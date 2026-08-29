from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings, get_settings
from app.database import AsyncSessionLocal
from app.models import ChatSession
from app.models.m1 import now_utc
from app.services.chat.service import stream_chat_answer
from app.services.model_service import HttpOllamaClient

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = REPO_ROOT / "docs" / "evals" / "wiki"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "qa-evals"


@dataclass(frozen=True, slots=True)
class QaQuestion:
    suite_id: str
    id: str
    question: str
    expected_behavior: str
    expected_answer_contains: list[str]
    expected_citation_terms: list[str]
    expected_sources: dict[str, Any]
    must_not_contain: list[str]


@dataclass(slots=True)
class QaResult:
    suite_id: str
    question_id: str
    question: str
    passed: bool
    answer: str
    citations: list[dict[str, Any]]
    trace_id: str | None
    failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QaTotals:
    answer_total: int = 0
    answer_required_term_hit: int = 0
    no_answer_total: int = 0
    no_answer_passed: int = 0
    citation_min_count_total: int = 0
    citation_min_count_passed: int = 0
    citation_grounding_total: int = 0
    citation_grounding_hit: int = 0
    retrieval_expected_source_total: int = 0
    retrieval_expected_source_hit: int = 0
    wiki_boost_total: int = 0
    wiki_boost_hit: int = 0
    graph_context_total: int = 0
    graph_context_hit: int = 0
    forbidden_answer_content_count: int = 0

    def metrics(self, *, total: int, passed: int) -> dict[str, float | int]:
        return {
            "qa_pass_rate": ratio(passed, total),
            "answer_required_term_hit_rate": ratio(self.answer_required_term_hit, self.answer_total),
            "no_answer_pass_rate": ratio(self.no_answer_passed, self.no_answer_total),
            "citation_min_count_pass_rate": ratio(
                self.citation_min_count_passed,
                self.citation_min_count_total,
            ),
            "citation_grounding_hit_rate": ratio(self.citation_grounding_hit, self.citation_grounding_total),
            "retrieval_expected_source_hit_rate": ratio(
                self.retrieval_expected_source_hit,
                self.retrieval_expected_source_total,
            ),
            "wiki_boost_hit_rate": ratio(self.wiki_boost_hit, self.wiki_boost_total),
            "graph_context_hit_rate": ratio(self.graph_context_hit, self.graph_context_total),
            "forbidden_answer_content_count": self.forbidden_answer_content_count,
        }


def ratio(hit: int, total: int) -> float:
    if total == 0:
        return 1.0
    return round(hit / total, 4)


def load_questions(dataset_root: Path, suite_ids: list[str] | None = None) -> list[QaQuestion]:
    selected = set(suite_ids or [])
    paths = sorted((dataset_root / "cases").glob("*/case.yaml"))
    paths.extend(sorted((dataset_root / "scenarios").glob("*/scenario.yaml")))
    if selected:
        paths = [path for path in paths if path.parent.name in selected]
    missing = selected - {path.parent.name for path in paths}
    if missing:
        raise ValueError(f"suite not found: {', '.join(sorted(missing))}")

    questions: list[QaQuestion] = []
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a YAML object")
        suite_id = str(data.get("id") or path.parent.name)
        for item in data.get("questions") or []:
            if not isinstance(item, dict) or not item.get("id") or not item.get("question"):
                raise ValueError(f"{path} contains invalid question entry")
            questions.append(
                QaQuestion(
                    suite_id=suite_id,
                    id=str(item["id"]),
                    question=str(item["question"]),
                    expected_behavior=str(item.get("expected_behavior") or "answer"),
                    expected_answer_contains=[str(term) for term in item.get("expected_answer_contains") or []],
                    expected_citation_terms=[str(term) for term in item.get("expected_citation_terms") or []],
                    expected_sources=dict(item.get("expected_sources") or {}),
                    must_not_contain=[str(term) for term in item.get("must_not_contain") or []],
                )
            )
    return questions


async def run_questions(
    questions: list[QaQuestion],
    *,
    settings: Settings,
    workspace_id: str,
    user_id: str,
    kb_id: str,
) -> dict[str, Any]:
    results: list[QaResult] = []
    async with AsyncSessionLocal() as session:
        for question in questions:
            chat_session = ChatSession(
                workspace_id=workspace_id,
                user_id=user_id,
                kb_id=kb_id,
                title=f"QA Eval {question.id}",
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(chat_session)
            await session.commit()
            answer, citations, trace_id = await collect_stream(
                stream_chat_answer(
                    session,
                    settings=settings,
                    ollama_client=HttpOllamaClient(),
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    session_id=chat_session.id,
                    question=question.question,
                )
            )
            results.append(evaluate_question(question, answer=answer, citations=citations, trace_id=trace_id))

    totals = QaTotals()
    for question, result in zip(questions, results, strict=True):
        add_question_totals(totals, question, result)
    passed = sum(1 for result in results if result.passed)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "workspace_id": workspace_id,
        "kb_id": kb_id,
        "question_count": len(results),
        "passed_question_count": passed,
        "metrics": totals.metrics(total=len(results), passed=passed),
        "results": [asdict(result) for result in results],
    }


async def collect_stream(stream: AsyncIterator[str]) -> tuple[str, list[dict[str, Any]], str | None]:
    answer = ""
    citations: list[dict[str, Any]] = []
    trace_id: str | None = None
    async for chunk in stream:
        for event, data in parse_sse(chunk):
            if event == "token":
                answer += str(data.get("content") or "")
            if event == "done":
                raw_citations = data.get("citations")
                citations = raw_citations if isinstance(raw_citations, list) else []
                raw_trace_id = data.get("trace_id")
                trace_id = str(raw_trace_id) if raw_trace_id else None
    return answer, citations, trace_id


def parse_sse(chunk: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in chunk.strip().split("\n\n"):
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data = line.removeprefix("data:").strip()
        if event and data:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = {}
            events.append((event, payload))
    return events


def evaluate_question(
    question: QaQuestion,
    *,
    answer: str,
    citations: list[dict[str, Any]],
    trace_id: str | None,
) -> QaResult:
    failures: list[str] = []
    if question.expected_behavior == "no_answer" and not re.search(r"无法|没有足够证据|不能确认", answer):
        failures.append("expected no-answer fallback")
    for term in question.expected_answer_contains:
        if term not in answer:
            failures.append(f"answer missing required term: {term}")
    citation_text = "\n".join(str(item.get("snippet") or "") for item in citations)
    for term in question.expected_citation_terms:
        if term not in citation_text:
            failures.append(f"citation missing grounding term: {term}")
    min_sources = int(question.expected_sources.get("min_count") or 0)
    if len(citations) < min_sources:
        failures.append(f"citation count below minimum: {len(citations)} < {min_sources}")
    allowed_types = set(question.expected_sources.get("allowed_types") or [])
    if allowed_types and any(item.get("source_type") not in allowed_types for item in citations):
        failures.append("citation source type outside allowed_types")
    for term in question.must_not_contain:
        count = answer.count(term)
        if count:
            failures.append(f"forbidden answer content found {count} time(s): {term}")
    return QaResult(
        suite_id=question.suite_id,
        question_id=question.id,
        question=question.question,
        passed=not failures,
        answer=answer,
        citations=citations,
        trace_id=trace_id,
        failures=failures,
    )


def add_question_totals(totals: QaTotals, question: QaQuestion, result: QaResult) -> None:
    if question.expected_behavior == "answer":
        totals.answer_total += len(question.expected_answer_contains)
        totals.answer_required_term_hit += sum(1 for term in question.expected_answer_contains if term in result.answer)
    else:
        totals.no_answer_total += 1
        if re.search(r"无法|没有足够证据|不能确认", result.answer):
            totals.no_answer_passed += 1

    totals.citation_min_count_total += 1
    if len(result.citations) >= int(question.expected_sources.get("min_count") or 0):
        totals.citation_min_count_passed += 1

    citation_text = "\n".join(str(item.get("snippet") or "") for item in result.citations)
    totals.citation_grounding_total += len(question.expected_citation_terms)
    totals.citation_grounding_hit += sum(1 for term in question.expected_citation_terms if term in citation_text)

    totals.retrieval_expected_source_total += 1
    allowed_types = set(question.expected_sources.get("allowed_types") or [])
    if not allowed_types or any(item.get("source_type") in allowed_types for item in result.citations):
        totals.retrieval_expected_source_hit += 1

    totals.wiki_boost_total += 1
    if any(item.get("source_type") == "wiki_page" for item in result.citations):
        totals.wiki_boost_hit += 1

    totals.graph_context_total += 1
    if any(item.get("source_type") == "wiki_page" for item in result.citations):
        totals.graph_context_hit += 1

    for term in question.must_not_contain:
        totals.forbidden_answer_content_count += result.answer.count(term)


def write_report(report: dict[str, Any], output_dir: Path, run_id: str) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"qa-eval-{run_id}.json"
    md_path = output_dir / f"qa-eval-{run_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# QA Eval Report",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- KB：{report['kb_id']}",
        f"- 问题数：{report['question_count']}",
        f"- 通过问题：{report['passed_question_count']}",
        "",
        "## 指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
    ]
    for name, value in report["metrics"].items():
        lines.append(f"| `{name}` | {value} |")
    lines.extend(["", "## 失败问题", ""])
    for item in report["results"]:
        if item["passed"]:
            continue
        lines.append(f"### {item['suite_id']} / {item['question_id']}")
        lines.append("")
        for failure in item["failures"]:
            lines.append(f"- {failure}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenWiki M5 QA evals against an existing KB.")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--suite", action="append", dest="suite_ids")
    parser.add_argument("--workspace-id")
    parser.add_argument("--user-id")
    parser.add_argument("--kb-id")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


async def async_main(argv: list[str]) -> int:
    args = parse_args(argv)
    questions = load_questions(args.dataset_root, args.suite_ids)
    if args.dry_run:
        print(f"validated {len(questions)} questions")
        return 0
    missing = [name for name in ("workspace_id", "user_id", "kb_id") if getattr(args, name) is None]
    if missing:
        raise SystemExit(f"missing required args: {', '.join('--' + name.replace('_', '-') for name in missing)}")
    report = await run_questions(
        questions,
        settings=get_settings(),
        workspace_id=args.workspace_id,
        user_id=args.user_id,
        kb_id=args.kb_id,
    )
    report["report_paths"] = write_report(report, args.output_dir, args.run_id)
    print(json.dumps({"metrics": report["metrics"], "report_paths": report["report_paths"]}, ensure_ascii=False))
    return 0 if report["metrics"]["qa_pass_rate"] == 1.0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
