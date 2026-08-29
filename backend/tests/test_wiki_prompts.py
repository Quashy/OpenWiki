import asyncio

from app.services.llm.base import LLMProvider
from app.services.llm.openai_provider import build_response_metadata
from app.services.wiki.pipeline import ObservedLLMProvider
from app.services.wiki.prompts import (
    PROMPT_FAMILY,
    PROMPT_VERSION,
    WikiPrompt,
    build_citation_prompt,
    build_dedup_prompt,
    build_extract_prompt,
    build_overview_prompt,
    build_reduce_prompt,
    build_source_summary_prompt,
    build_taxonomy_prompt,
)


class CapturingSpan:
    def __init__(self, *, name: str, metadata: dict[str, object]) -> None:
        self.name = name
        self.metadata = metadata
        self.updates: list[dict[str, object]] = []

    def __enter__(self) -> "CapturingSpan":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)


class CapturingTrace:
    def __init__(self) -> None:
        self.spans: list[CapturingSpan] = []

    def span(self, *, name: str, metadata: dict[str, object]) -> CapturingSpan:
        span = CapturingSpan(name=name, metadata=metadata)
        self.spans.append(span)
        return span


class StaticLLMProvider(LLMProvider):
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        return "{}"


class MetadataLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_response_metadata = {
            "llm_response_model": "deepseek-v4-flash",
            "llm_response_finish_reason": "stop",
            "llm_response_usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "llm_response_choice_metadata": {"index": 0, "finish_reason": "stop"},
            "llm_response_content_empty": False,
        }

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        return "{}"


def sample_prompts() -> list[WikiPrompt]:
    chunk = {"id": "chunk-1", "header_path": ["产品"], "content": "晨光咖啡使用 CG Coffee 收银系统。"}
    candidate = {
        "name": "晨光咖啡",
        "slug": "entity/morning-light-cafe",
        "page_type": "entity",
        "entity_type": "place",
        "aliases": ["CG Coffee"],
        "description": "晨光咖啡是一家社区咖啡店。",
    }
    return [
        build_extract_prompt(document_id="doc-1", existing_slugs=[], chunks=[chunk]),
        build_dedup_prompt(new_candidates=[candidate], existing_pages=[]),
        build_citation_prompt(candidates=[candidate], chunks=[chunk]),
        build_taxonomy_prompt(candidates=[candidate]),
        build_source_summary_prompt(document_id="doc-1", allowed_links=[candidate], chunks=[chunk]),
        build_reduce_prompt(candidate=candidate, allowed_links=[candidate], chunks=[chunk]),
        build_overview_prompt(allowed_links=[candidate], page_summaries=[{"slug": candidate["slug"], "title": candidate["name"], "summary": candidate["description"]}]),
    ]


def test_wiki_prompt_builders_render_version_metadata_and_no_placeholders() -> None:
    prompts = sample_prompts()
    stages = ["extract", "dedup", "citation", "taxonomy", "source_summary", "reduce", "overview"]

    assert [prompt.metadata["prompt_stage"] for prompt in prompts] == stages
    for prompt in prompts:
        assert prompt.metadata["prompt_family"] == PROMPT_FAMILY
        assert prompt.metadata["prompt_version"] == PROMPT_VERSION
        assert PROMPT_VERSION == "wiki_prompt_v0.3"
        assert "{{" not in prompt.system
        assert "{{" not in prompt.user
        assert "}}" not in prompt.system
        assert "}}" not in prompt.user


def test_wiki_prompt_builders_keep_required_output_contracts() -> None:
    extract, dedup, citation, taxonomy, source_summary, reduce, overview = sample_prompts()

    assert "<stage>extract</stage>" in extract.user
    assert '"candidates"' in extract.user
    assert "entity/..." in extract.user
    assert "concept/..." in extract.user
    assert "slug 必须表达对象本身" in extract.user
    assert "aliases 必须覆盖输入中明确指向同一对象的所有名称写法" in extract.user
    assert "编号、订单号、预约号、取件码、车次号、合同号、工单号" in extract.user

    assert "<stage>dedup</stage>" in dedup.user
    assert '"merges"' in dedup.user
    assert "related != same" in dedup.user

    assert "<stage>citation</stage>" in citation.user
    assert '"citations"' in citation.user
    assert '"chunk_ids"' in citation.user
    assert "chunk_id 必须逐字来自 chunks_json 的 id" in citation.user
    assert "不要只看 canonical name" in citation.user
    assert "关键参数、冲突事实或关系来自不同 chunk" in citation.user

    assert "<stage>taxonomy</stage>" in taxonomy.user
    assert '"category_path"' in taxonomy.user
    assert "最多两级" in taxonomy.user

    assert "<stage>source_summary</stage>" in source_summary.user
    assert "SUMMARY: ..." in source_summary.system
    assert "## Key Takeaways" in source_summary.user

    assert "<stage>reduce</stage>" in reduce.user
    assert '"content"' in reduce.user
    assert '"relations"' in reduce.user
    assert "不得链接到 candidate_json 自己的 slug" in reduce.user
    assert "必须原样保留 chunks 明确给出的关键事实" in reduce.user
    assert "计划与配套模板/记录" in reduce.user

    assert "<stage>overview</stage>" in overview.user
    assert "不要生成索引目录清单" in overview.user
    assert "只能使用白名单双链" in overview.system


def test_observed_llm_span_records_prompt_version_metadata() -> None:
    trace = CapturingTrace()
    llm = ObservedLLMProvider(StaticLLMProvider(), trace)
    prompt = sample_prompts()[0]

    asyncio.run(
        llm.complete(
            [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
            temperature=0.2,
            timeout_seconds=60,
            prompt_metadata=prompt.metadata,
        )
    )

    assert len(trace.spans) == 1
    assert trace.spans[0].name == "llm_extract"
    assert trace.spans[0].metadata["prompt_family"] == "wiki_ingest"
    assert trace.spans[0].metadata["prompt_stage"] == "extract"
    assert trace.spans[0].metadata["prompt_version"] == "wiki_prompt_v0.3"


def test_observed_llm_span_updates_response_metadata() -> None:
    trace = CapturingTrace()
    llm = ObservedLLMProvider(MetadataLLMProvider(), trace)
    prompt = sample_prompts()[0]

    asyncio.run(
        llm.complete(
            [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
            temperature=0.2,
            timeout_seconds=60,
            prompt_metadata=prompt.metadata,
        )
    )

    assert trace.spans[0].updates
    metadata = trace.spans[0].updates[-1]["metadata"]
    assert metadata["prompt_version"] == "wiki_prompt_v0.3"
    assert metadata["llm_response_model"] == "deepseek-v4-flash"
    assert metadata["llm_response_finish_reason"] == "stop"
    assert metadata["llm_response_usage"]["total_tokens"] == 12
    assert metadata["llm_response_choice_metadata"] == {"index": 0, "finish_reason": "stop"}


def test_build_response_metadata_keeps_choice_diagnostics_without_message_content() -> None:
    metadata = build_response_metadata(
        {
            "id": "chatcmpl-1",
            "model": "deepseek-v4-flash",
            "created": 1798500000,
            "usage": {"prompt_tokens": 100, "completion_tokens": 0, "total_tokens": 100},
        },
        {
            "index": 0,
            "finish_reason": "content_filter",
            "message": {"role": "assistant", "content": "", "refusal": "filtered"},
        },
        "",
        http_status_code=200,
    )

    assert metadata["llm_response_http_status"] == 200
    assert metadata["llm_response_id"] == "chatcmpl-1"
    assert metadata["llm_response_model"] == "deepseek-v4-flash"
    assert metadata["llm_response_finish_reason"] == "content_filter"
    assert metadata["llm_response_usage"]["prompt_tokens"] == 100
    assert metadata["llm_response_choice_metadata"] == {"index": 0, "finish_reason": "content_filter"}
    assert metadata["llm_response_message_metadata"] == {"role": "assistant", "refusal": "filtered"}
    assert metadata["llm_response_content_length"] == 0
    assert metadata["llm_response_content_empty"] is True
