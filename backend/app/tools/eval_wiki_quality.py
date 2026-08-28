from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import AsyncSessionLocal
from app.models import (
    Document,
    Entity,
    KnowledgeBase,
    ModelSetting,
    Relation,
    TaskPendingOp,
    User,
    WikiPage,
    Workspace,
    WorkspaceMember,
)
from app.models.m1 import new_uuid, now_utc
from app.security import hash_password
from app.services.document_service import process_document_job, sanitize_filename
from app.services.kb_service import create_kb
from app.services.llm.deepseek_provider import DeepSeekLLMProvider
from app.services.model_service import HttpOllamaClient
from app.services.wiki.page_service import DOUBLE_LINK_RE, full_markdown
from app.services.wiki.pipeline import process_wiki_ingest_job
from app.services.wiki.prompts import PROMPT_FAMILY, PROMPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = REPO_ROOT / "docs" / "evals" / "wiki"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "wiki-evals"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


@dataclass(frozen=True, slots=True)
class WikiEvalCase:
    id: str
    title: str
    purpose: str
    tags: list[str]
    wiki_config: dict[str, Any]
    documents: list[dict[str, str]]
    expectations: dict[str, Any]
    root: Path


@dataclass(slots=True)
class MetricTotals:
    must_have_pages_total: int = 0
    must_have_pages_hit: int = 0
    forbidden_page_violation_count: int = 0
    aliases_total: int = 0
    aliases_hit: int = 0
    citation_requirements_total: int = 0
    citation_requirements_passed: int = 0
    relations_total: int = 0
    relations_hit: int = 0
    dead_link_count: int = 0
    self_loop_count: int = 0
    forbidden_content_count: int = 0
    required_terms_total: int = 0
    required_terms_hit: int = 0

    def metrics(self, *, total_cases: int, passed_cases: int) -> dict[str, float | int]:
        return {
            "pass_rate": ratio(passed_cases, total_cases),
            "must_have_page_hit_rate": ratio(self.must_have_pages_hit, self.must_have_pages_total),
            "forbidden_page_violation_count": self.forbidden_page_violation_count,
            "alias_hit_rate": ratio(self.aliases_hit, self.aliases_total),
            "citation_requirement_pass_rate": ratio(
                self.citation_requirements_passed,
                self.citation_requirements_total,
            ),
            "relation_hit_rate": ratio(self.relations_hit, self.relations_total),
            "dead_link_count": self.dead_link_count,
            "self_loop_count": self.self_loop_count,
            "forbidden_content_count": self.forbidden_content_count,
            "required_term_hit_rate": ratio(self.required_terms_hit, self.required_terms_total),
        }

    def add(self, other: MetricTotals) -> None:
        self.must_have_pages_total += other.must_have_pages_total
        self.must_have_pages_hit += other.must_have_pages_hit
        self.forbidden_page_violation_count += other.forbidden_page_violation_count
        self.aliases_total += other.aliases_total
        self.aliases_hit += other.aliases_hit
        self.citation_requirements_total += other.citation_requirements_total
        self.citation_requirements_passed += other.citation_requirements_passed
        self.relations_total += other.relations_total
        self.relations_hit += other.relations_hit
        self.dead_link_count += other.dead_link_count
        self.self_loop_count += other.self_loop_count
        self.forbidden_content_count += other.forbidden_content_count
        self.required_terms_total += other.required_terms_total
        self.required_terms_hit += other.required_terms_hit


@dataclass(slots=True)
class CaseResult:
    id: str
    title: str
    passed: bool
    metrics: dict[str, float | int]
    totals: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
    workspace_id: str | None = None
    source_kb_id: str | None = None
    wiki_kb_id: str | None = None
    page_count: int = 0
    generated_pages: list[dict[str, Any]] = field(default_factory=list)
    prompt_family: str = PROMPT_FAMILY
    prompt_version: str = PROMPT_VERSION
    llm_model: str = DEFAULT_DEEPSEEK_MODEL
    embedding_model: str = ""


def ratio(hit: int, total: int) -> float:
    if total == 0:
        return 1.0
    return round(hit / total, 4)


def load_cases(dataset_root: Path, case_ids: list[str] | None = None) -> list[WikiEvalCase]:
    cases_root = dataset_root / "cases"
    if not cases_root.exists():
        raise ValueError(f"cases directory not found: {cases_root}")

    selected = set(case_ids or [])
    paths = sorted(cases_root.glob("*/case.yaml"))
    if selected:
        paths = [path for path in paths if path.parent.name in selected]
    missing = selected - {path.parent.name for path in paths}
    if missing:
        raise ValueError(f"case not found: {', '.join(sorted(missing))}")
    return [load_case(path) for path in paths]


def load_case(path: Path) -> WikiEvalCase:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")

    required = {"id", "title", "purpose", "tags", "wiki_config", "documents", "expectations"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{path} missing fields: {', '.join(missing)}")
    if data["id"] != path.parent.name:
        raise ValueError(f"{path} id must match directory name")
    if not isinstance(data["documents"], list) or not data["documents"]:
        raise ValueError(f"{path} documents must be a non-empty list")

    expectations = data["expectations"]
    if not isinstance(expectations, dict):
        raise ValueError(f"{path} expectations must be an object")
    expectation_fields = {
        "must_have_pages",
        "must_not_have_pages",
        "must_have_aliases",
        "must_have_citations",
        "must_have_relations",
        "must_not_contain",
        "max_dead_links",
        "max_self_loops",
    }
    missing_expectations = sorted(expectation_fields - set(expectations))
    if missing_expectations:
        raise ValueError(f"{path} expectations missing fields: {', '.join(missing_expectations)}")

    for document in data["documents"]:
        if not isinstance(document, dict) or not document.get("path"):
            raise ValueError(f"{path} documents entries must include path")
        document_path = path.parent / str(document["path"])
        if not document_path.exists():
            raise ValueError(f"document not found: {document_path}")

    return WikiEvalCase(
        id=str(data["id"]),
        title=str(data["title"]),
        purpose=str(data["purpose"]),
        tags=[str(tag) for tag in data["tags"]],
        wiki_config=dict(data["wiki_config"]),
        documents=[dict(document) for document in data["documents"]],
        expectations=expectations,
        root=path.parent,
    )


async def run_eval(
    cases: list[WikiEvalCase],
    *,
    settings: Settings,
    output_dir: Path,
    run_id: str,
    model: str,
    embedding_model: str,
    ollama_base_url: str,
    fail_fast: bool,
) -> dict[str, Any]:
    results: list[CaseResult] = []
    for case in cases:
        try:
            results.append(
                await run_case(
                    case,
                    settings=settings,
                    run_id=run_id,
                    model=model,
                    embedding_model=embedding_model,
                    ollama_base_url=ollama_base_url,
                )
            )
        except Exception as exc:
            result = CaseResult(
                id=case.id,
                title=case.title,
                passed=False,
                metrics=MetricTotals().metrics(total_cases=1, passed_cases=0),
                error=str(exc),
                failures=[f"case execution failed: {exc}"],
            )
            results.append(result)
            if fail_fast:
                break

    report = build_report(
        run_id=run_id,
        cases=cases,
        results=results,
        model=model,
        embedding_model=embedding_model,
        ollama_base_url=ollama_base_url,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"wiki-eval-{run_id}.json"
    md_path = output_dir / f"wiki-eval-{run_id}.md"
    report["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return report


async def run_case(
    case: WikiEvalCase,
    *,
    settings: Settings,
    run_id: str,
    model: str,
    embedding_model: str,
    ollama_base_url: str,
) -> CaseResult:
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is required for real LLM eval")

    ollama_client = HttpOllamaClient()
    async with AsyncSessionLocal() as session:
        await configure_eval_ollama(session, ollama_base_url=ollama_base_url)
        username = f"eval_{case.id}_{run_id}"[:64]
        username = f"{username[:55]}_{new_uuid()[:8]}"
        user = User(username=username, password_hash=hash_password(new_uuid()))
        session.add(user)
        await session.flush()
        workspace = Workspace(name=f"Wiki Eval {case.id} {run_id}", created_by=user.id)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
        await session.commit()

        source_kb = await create_kb(
            session,
            settings=settings,
            client=ollama_client,
            workspace_id=workspace.id,
            actor_id=user.id,
            payload={
                "type": "document",
                "name": f"eval-source-{case.id}-{run_id}",
                "description": case.purpose,
                "embedding_model_tag": embedding_model,
            },
        )
        wiki_kb = await create_kb(
            session,
            settings=settings,
            client=ollama_client,
            workspace_id=workspace.id,
            actor_id=user.id,
            payload={
                "type": "wiki",
                "name": f"eval-wiki-{case.id}-{run_id}",
                "description": case.purpose,
                "embedding_model_tag": embedding_model,
                "source_knowledge_base_ids": [source_kb.id],
                "wiki_config": case.wiki_config,
            },
        )

        document_ids = await create_case_documents(
            session,
            settings=settings,
            case=case,
            run_id=run_id,
            source_kb_id=source_kb.id,
            actor_id=user.id,
            actor_username=username,
        )
        for document_id in document_ids:
            await process_document_job(
                session,
                settings=settings,
                client=ollama_client,
                document_id=document_id,
            )

        task = TaskPendingOp(
            kb_id=wiki_kb.id,
            task_type="wiki_ingest",
            status="pending",
            stage="pending",
            progress=0,
            payload={
                "actor_id": user.id,
                "workspace_id": workspace.id,
                "document_ids": [],
                "rebuild": False,
                "eval_case_id": case.id,
                "eval_run_id": run_id,
                "prompt_family": PROMPT_FAMILY,
                "prompt_version": PROMPT_VERSION,
                "llm_model": model,
                "embedding_model": embedding_model,
            },
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(task)
        await session.commit()

        llm_provider = DeepSeekLLMProvider(
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            model=model,
            default_temperature=float(case.wiki_config.get("temperature", 0.2)),
            default_timeout_seconds=int(case.wiki_config.get("llm_timeout_seconds", 60)),
        )
        await process_wiki_ingest_job(
            session,
            settings=settings,
            ollama_client=ollama_client,
            task_id=task.id,
            llm_provider=llm_provider,
        )

        task = await session.get(TaskPendingOp, task.id)
        pages = list(
            (
                await session.execute(
                    select(WikiPage).where(WikiPage.kb_id == wiki_kb.id).order_by(WikiPage.slug)
                )
            ).scalars()
        )
        entities = list((await session.execute(select(Entity).where(Entity.kb_id == wiki_kb.id))).scalars())
        relations = list((await session.execute(select(Relation).where(Relation.kb_id == wiki_kb.id))).scalars())
        source_documents = list(
            (await session.execute(select(Document).where(Document.kb_id == source_kb.id))).scalars()
        )

        evaluated = evaluate_case(
            case,
            pages=pages,
            entities=entities,
            relations=relations,
        )
        generated_pages = [
            {
                "slug": page.slug,
                "title": page.title,
                "page_type": page.page_type,
                "aliases": list(page.aliases or []),
                "source_ref_count": len(page.source_refs or []),
                "summary": page.summary,
            }
            for page in pages
        ]
        return CaseResult(
            id=case.id,
            title=case.title,
            passed=evaluated["passed"],
            metrics=evaluated["metrics"],
            totals=asdict(evaluated["totals"]),
            failures=evaluated["failures"],
            task_id=task.id if task else None,
            trace_id=(task.payload or {}).get("trace_id") if task else None,
            workspace_id=workspace.id,
            source_kb_id=source_kb.id,
            wiki_kb_id=wiki_kb.id,
            page_count=len(pages),
            generated_pages=generated_pages,
            prompt_family=PROMPT_FAMILY,
            prompt_version=PROMPT_VERSION,
            llm_model=model,
            embedding_model=embedding_model,
        )


async def configure_eval_ollama(session: AsyncSession, *, ollama_base_url: str) -> None:
    row = await session.get(ModelSetting, "global")
    if row is None:
        row = ModelSetting(id="global", ollama_base_url=ollama_base_url)
        session.add(row)
    else:
        row.ollama_base_url = ollama_base_url
    await session.commit()


async def create_case_documents(
    session: AsyncSession,
    *,
    settings: Settings,
    case: WikiEvalCase,
    run_id: str,
    source_kb_id: str,
    actor_id: str,
    actor_username: str,
) -> list[str]:
    document_ids: list[str] = []
    target_dir = settings.upload_dir / "wiki-evals" / run_id / case.id
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in case.documents:
        source_path = case.root / item["path"]
        content = source_path.read_bytes()
        filename = sanitize_filename(source_path.name)
        document = Document(
            kb_id=source_kb_id,
            filename=filename,
            file_hash=hashlib.sha256(content).hexdigest(),
            file_path="",
            file_size=len(content),
            status="pending",
            error_message=None,
            chunk_count=0,
            created_by=actor_id,
            created_by_username=actor_username,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(document)
        await session.flush()
        target_path = target_dir / f"{document.id}-{filename}"
        target_path.write_bytes(content)
        document.file_path = str(target_path)
        document_ids.append(document.id)
    await session.commit()
    return document_ids


def evaluate_case(
    case: WikiEvalCase,
    *,
    pages: list[WikiPage],
    entities: list[Entity],
    relations: list[Relation],
) -> dict[str, Any]:
    expectations = case.expectations
    totals = MetricTotals()
    failures: list[str] = []
    pages_by_slug = {page.slug: page for page in pages}
    entities_by_slug = {entity.slug: entity for entity in entities}
    entities_by_id = {entity.id: entity for entity in entities}
    page_text_by_slug = {page.slug: page_text(page) for page in pages}

    for expected in expectations.get("must_have_pages", []):
        slug = str(expected["slug"])
        totals.must_have_pages_total += 1
        page = pages_by_slug.get(slug)
        hit = page is not None
        if hit and expected.get("page_type"):
            hit = page.page_type == expected["page_type"]
        if hit and expected.get("title_contains"):
            hit = str(expected["title_contains"]) in page.title
        if hit:
            totals.must_have_pages_hit += 1
        else:
            failures.append(f"missing expected page: {slug}")

    for item in expectations.get("must_not_have_pages", []):
        slug = str(item["slug"] if isinstance(item, dict) else item)
        if slug in pages_by_slug:
            totals.forbidden_page_violation_count += 1
            failures.append(f"forbidden page exists: {slug}")

    for slug, aliases in expectations.get("must_have_aliases", {}).items():
        page = pages_by_slug.get(str(slug))
        actual = set(page.aliases or []) if page is not None else set()
        for alias in aliases:
            totals.aliases_total += 1
            if alias in actual:
                totals.aliases_hit += 1
            else:
                failures.append(f"missing alias on {slug}: {alias}")

    for slug, requirement in expectations.get("must_have_citations", {}).items():
        page = pages_by_slug.get(str(slug))
        min_count = int(requirement.get("min_count", 1))
        totals.citation_requirements_total += 1
        if page is not None and len(page.source_refs or []) >= min_count:
            totals.citation_requirements_passed += 1
        else:
            failures.append(f"citation requirement failed on {slug}: min_count={min_count}")
        for term in requirement.get("required_terms", []):
            totals.required_terms_total += 1
            if page is not None and str(term) in page_text_by_slug.get(str(slug), ""):
                totals.required_terms_hit += 1
            else:
                failures.append(f"missing required term on {slug}: {term}")

    for expected in expectations.get("must_have_relations", []):
        source_slug = str(expected["source_slug"])
        target_slug = str(expected["target_slug"])
        relation_type_contains = expected.get("relation_type_contains")
        totals.relations_total += 1
        if relation_exists(
            source_slug=source_slug,
            target_slug=target_slug,
            relation_type_contains=relation_type_contains,
            entities_by_slug=entities_by_slug,
            relations=relations,
        ):
            totals.relations_hit += 1
        else:
            failures.append(f"missing relation: {source_slug} -> {target_slug}")

    valid_slugs = set(pages_by_slug)
    for page in pages:
        for target_slug, _label in DOUBLE_LINK_RE.findall(page.content):
            if target_slug not in valid_slugs:
                totals.dead_link_count += 1
                failures.append(f"dead link on {page.slug}: {target_slug}")

    for relation in relations:
        source = entities_by_id.get(relation.source_entity_id)
        target = entities_by_id.get(relation.target_entity_id)
        if source is not None and target is not None and source.slug == target.slug:
            totals.self_loop_count += 1
            failures.append(f"self loop relation: {source.slug}")

    all_page_text = "\n".join(page_text_by_slug.values())
    for forbidden in expectations.get("must_not_contain", []):
        count = all_page_text.count(str(forbidden))
        if count:
            totals.forbidden_content_count += count
            failures.append(f"forbidden content found {count} time(s): {forbidden}")

    max_dead_links = int(expectations.get("max_dead_links", 0))
    max_self_loops = int(expectations.get("max_self_loops", 0))
    passed = (
        totals.must_have_pages_hit == totals.must_have_pages_total
        and totals.forbidden_page_violation_count == 0
        and totals.aliases_hit == totals.aliases_total
        and totals.citation_requirements_passed == totals.citation_requirements_total
        and totals.relations_hit == totals.relations_total
        and totals.dead_link_count <= max_dead_links
        and totals.self_loop_count <= max_self_loops
        and totals.forbidden_content_count == 0
        and totals.required_terms_hit == totals.required_terms_total
    )
    return {
        "passed": passed,
        "metrics": totals.metrics(total_cases=1, passed_cases=1 if passed else 0),
        "failures": failures,
        "totals": totals,
    }


def relation_exists(
    *,
    source_slug: str,
    target_slug: str,
    relation_type_contains: str | None,
    entities_by_slug: dict[str, Entity],
    relations: list[Relation],
) -> bool:
    source = entities_by_slug.get(source_slug)
    target = entities_by_slug.get(target_slug)
    if source is None or target is None:
        return False
    for relation in relations:
        if relation.source_entity_id != source.id or relation.target_entity_id != target.id:
            continue
        if relation_type_contains and str(relation_type_contains) not in relation.relation_type:
            continue
        return True
    return False


def page_text(page: WikiPage) -> str:
    return full_markdown(page.summary, page.content)


def build_report(
    *,
    run_id: str,
    cases: list[WikiEvalCase],
    results: list[CaseResult],
    model: str,
    embedding_model: str,
    ollama_base_url: str,
) -> dict[str, Any]:
    totals = MetricTotals()
    for result in results:
        totals.add(totals_from_dict(result.totals))
    passed_cases = sum(1 for result in results if result.passed)
    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "prompt_family": PROMPT_FAMILY,
        "prompt_version": PROMPT_VERSION,
        "llm_provider": "deepseek",
        "llm_model": model,
        "embedding_provider": "ollama",
        "embedding_model": embedding_model,
        "ollama_base_url": ollama_base_url,
        "case_count": len(results),
        "passed_case_count": passed_cases,
        "metrics": totals.metrics(total_cases=len(results), passed_cases=passed_cases),
        "trace_ids": [result.trace_id for result in results if result.trace_id],
        "cases": [asdict(result) for result in results],
    }


def totals_from_dict(data: dict[str, int]) -> MetricTotals:
    return MetricTotals(**{field_name: int(data.get(field_name, 0)) for field_name in MetricTotals.__dataclass_fields__})


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Wiki Eval Report {report['run_id']}",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- Prompt：{report['prompt_family']} / {report['prompt_version']}",
        f"- LLM：{report['llm_provider']} / {report['llm_model']}",
        f"- Embedding：{report['embedding_provider']} / {report['embedding_model']}",
        f"- Case 数：{report['case_count']}",
        f"- 通过 Case：{report['passed_case_count']}",
        "",
        "## 指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
    ]
    for name, value in report["metrics"].items():
        lines.append(f"| `{name}` | {value} |")

    lines.extend(["", "## Case 结果", ""])
    for item in report["cases"]:
        status = "PASS" if item["passed"] else "FAIL"
        lines.extend(
            [
                f"### {item['id']} - {status}",
                "",
                f"- 标题：{item['title']}",
                f"- 页面数：{item['page_count']}",
                f"- task_id：{item.get('task_id') or ''}",
                f"- trace_id：{item.get('trace_id') or ''}",
            ]
        )
        if item.get("error"):
            lines.append(f"- error：{item['error']}")
        if item["failures"]:
            lines.append("- 失败断言：")
            lines.extend(f"  - {failure}" for failure in item["failures"])
        lines.extend(["", "关键页面："])
        for page in item["generated_pages"][:8]:
            lines.append(f"- `{page['slug']}` ({page['page_type']}): {page['title']} - {page['summary']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic Wiki quality evals with DeepSeek.")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--case", action="append", dest="case_ids", help="Run a single case id. Repeatable.")
    parser.add_argument("--model", default=DEFAULT_DEEPSEEK_MODEL)
    parser.add_argument("--embedding-model", default=None)
    parser.add_argument("--ollama-base-url", default=None)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--dry-run", action="store_true", help="Validate dataset files without DB or LLM calls.")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


async def async_main(argv: list[str]) -> int:
    args = parse_args(argv)
    cases = load_cases(args.dataset_root, args.case_ids)
    if args.dry_run:
        document_count = sum(len(case.documents) for case in cases)
        print(f"validated {len(cases)} cases, {document_count} documents")
        return 0

    settings = get_settings()
    embedding_model = args.embedding_model or settings.ollama_embed_model
    ollama_base_url = args.ollama_base_url or settings.ollama_base_url
    report = await run_eval(
        cases,
        settings=settings,
        output_dir=args.output_dir,
        run_id=args.run_id,
        model=args.model,
        embedding_model=embedding_model,
        ollama_base_url=ollama_base_url,
        fail_fast=args.fail_fast,
    )
    print(json.dumps({"metrics": report["metrics"], "report_paths": report["report_paths"]}, ensure_ascii=False))
    return 0 if report["metrics"]["pass_rate"] == 1.0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
