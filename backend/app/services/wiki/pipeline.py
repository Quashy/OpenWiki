import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import structlog
from arq import create_pool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import Chunk, Document, Entity, KnowledgeBase, ModelSetting, TaskPendingOp, WikiPage, WikiSourceBinding
from app.models.m1 import now_utc
from app.schemas import TaskAcceptedResponse, WikiConfig
from app.security import decrypt_secret
from app.services.audit_service import record_audit
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider
from app.services.llm.base import LLMProvider
from app.services.llm.deepseek_provider import DeepSeekLLMProvider
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.model_service import HttpOllamaClient, OllamaClient, get_or_create_settings
from app.services.observability import Observability
from app.services.wiki.page_service import (
    clear_wiki_content,
    full_markdown,
    index_wiki_pages,
    require_wiki_kb,
    upsert_entity,
    upsert_relation,
    upsert_wiki_page,
)
from app.services.wiki.prompts import (
    WikiPrompt,
    build_citation_prompt,
    build_extract_prompt,
    build_overview_prompt,
    build_reduce_prompt,
    build_source_summary_prompt,
    build_taxonomy_prompt,
)
from app.workers.settings import redis_settings

logger = structlog.get_logger(__name__)

MAX_CANDIDATES = 16


@dataclass(frozen=True, slots=True)
class WikiCandidate:
    name: str
    slug: str
    page_type: str
    entity_type: str
    aliases: list[str]
    description: str
    source_refs: list[str]


async def enqueue_wiki_job(task_id: str) -> None:
    try:
        redis = await asyncio.wait_for(create_pool(redis_settings()), timeout=1)
        await asyncio.wait_for(redis.enqueue_job("wiki_ingest", task_id, _job_id=task_id), timeout=1)
        await redis.close()
    except Exception as exc:  # pragma: no cover - local dev/test may not run Redis
        logger.warning("wiki_enqueue_failed", task_id=task_id, error=str(exc))


async def create_wiki_task(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    task_type: str,
    document_ids: list[str] | None = None,
) -> TaskAcceptedResponse:
    kb = await require_wiki_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    running = await session.scalar(
        select(TaskPendingOp).where(
            TaskPendingOp.kb_id == kb_id,
            TaskPendingOp.task_type.in_(["wiki_ingest", "wiki_rebuild"]),
            TaskPendingOp.status.in_(["pending", "running"]),
        )
    )
    if running is not None:
        raise ApiError("wiki_ingest_running", "Wiki 正在更新中", 409)
    if task_type == "wiki_rebuild":
        kb.status = "building"
        kb.updated_at = now_utc()

    task = TaskPendingOp(
        kb_id=kb_id,
        task_type=task_type,
        status="pending",
        stage="pending",
        progress=0,
        payload={
            "actor_id": actor_id,
            "workspace_id": workspace_id,
            "document_ids": document_ids or [],
            "rebuild": task_type == "wiki_rebuild",
        },
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(task)
    await session.flush()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="wiki.rebuild" if task_type == "wiki_rebuild" else "wiki.ingest",
        resource_type="kb",
        resource_id=kb_id,
        details={"task_id": task.id, "document_ids": document_ids or []},
    )
    await session.commit()
    await enqueue_wiki_job(task.id)
    return TaskAcceptedResponse(task_id=task.id)


async def build_llm_provider(session: AsyncSession, *, settings: Settings) -> LLMProvider | None:
    row: ModelSetting = await get_or_create_settings(session, settings)
    encrypted_key = row.api_key_encrypted
    if encrypted_key:
        api_key = decrypt_secret(encrypted_key, settings)
        provider_name = row.provider
        base_url = row.base_url
        model = row.model
    elif settings.deepseek_api_key:
        api_key = settings.deepseek_api_key
        provider_name = "deepseek"
        base_url = settings.deepseek_base_url
        model = "deepseek-chat"
    elif settings.openai_api_key:
        api_key = settings.openai_api_key
        provider_name = "openai"
        base_url = settings.openai_base_url
        model = "gpt-4o-mini"
    else:
        return None

    kwargs = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "default_temperature": row.temperature,
        "default_timeout_seconds": row.timeout_seconds,
    }
    if provider_name == "deepseek":
        return DeepSeekLLMProvider(**kwargs)
    return OpenAILLMProvider(**kwargs)


async def process_wiki_ingest_job(
    session: AsyncSession,
    *,
    settings: Settings,
    ollama_client: OllamaClient,
    task_id: str,
    llm_provider: LLMProvider | None = None,
) -> None:
    task = await session.get(TaskPendingOp, task_id)
    if task is None:
        raise ApiError("not_found", "Wiki 任务不存在", 404)
    kb = await session.get(KnowledgeBase, task.kb_id)
    if kb is None or kb.type != "wiki":
        raise ApiError("not_found", "Wiki KB 不存在", 404)
    config = WikiConfig.model_validate(kb.wiki_config or {})
    llm = llm_provider if llm_provider is not None else await build_llm_provider(session, settings=settings)
    observability = Observability(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
    trace = observability.trace(
        name="wiki_ingest",
        metadata={
            "workspace_id": kb.workspace_id,
            "kb_id": kb.id,
            "task_id": task.id,
            "task_type": task.task_type,
            "actor_id": task.payload.get("actor_id"),
            "eval_case_id": task.payload.get("eval_case_id"),
            "eval_run_id": task.payload.get("eval_run_id"),
            "prompt_family": task.payload.get("prompt_family"),
            "prompt_version": task.payload.get("prompt_version"),
            "llm_model": task.payload.get("llm_model"),
        },
    )
    if llm is not None:
        llm = ObservedLLMProvider(llm, trace)
    task.payload = {**task.payload, "trace_id": trace.id}
    trace_level = "DEFAULT"
    trace_status_message = "completed"

    try:
        await update_task_state(session, task, status="running", stage="extracting", progress=10)
        if task.payload.get("rebuild"):
            await clear_wiki_content(session, kb_id=kb.id)
            await session.commit()

        documents = await source_documents_for_task(session, kb=kb, document_ids=task.payload.get("document_ids") or [])
        if not documents:
            raise ApiError("wiki_no_documents", "没有可摄入的已完成 Source 文档", 409)
        chunks_by_doc = await chunks_for_documents(session, [document.id for document in documents])
        existing_slugs = list((await session.execute(select(WikiPage.slug).where(WikiPage.kb_id == kb.id))).scalars())

        with trace.span(name="extract", metadata={"document_count": len(documents)}):
            candidates = await extract_candidates(
                llm,
                documents=documents,
                chunks_by_doc=chunks_by_doc,
                existing_slugs=existing_slugs,
                config=config,
            )
        await update_task_state(session, task, status="running", stage="citing", progress=25)

        with trace.span(name="citation", metadata={"candidate_count": len(candidates)}):
            citations = await cite_candidates(
                llm,
                candidates=candidates,
                chunks_by_doc=chunks_by_doc,
                config=config,
            )
        await update_task_state(session, task, status="running", stage="taxonomy", progress=40)

        with trace.span(name="taxonomy", metadata={"candidate_count": len(candidates)}):
            taxonomy = await plan_taxonomy(llm, candidates=candidates, config=config)
        await update_task_state(session, task, status="running", stage="summarizing", progress=55)

        with trace.span(name="summary", metadata={"document_count": len(documents)}):
            await write_source_pages(
                session,
                llm,
                kb=kb,
                documents=documents,
                chunks_by_doc=chunks_by_doc,
                candidates=candidates,
                config=config,
            )
        await update_task_state(session, task, status="running", stage="reducing", progress=70)

        with trace.span(name="reduce", metadata={"candidate_count": len(candidates)}):
            await write_candidate_pages(
                session,
                llm,
                kb=kb,
                candidates=candidates,
                citations=citations,
                taxonomy=taxonomy,
                chunks_by_doc=chunks_by_doc,
                config=config,
            )
        await update_task_state(session, task, status="running", stage="postprocessing", progress=88)

        with trace.span(name="postprocess", metadata={"candidate_count": len(candidates)}):
            await write_postprocess_pages(session, llm, kb=kb, candidates=candidates, config=config)
            await embed_wiki_pages(session, settings=settings, ollama_client=ollama_client, kb=kb)

        kb.status = "active"
        kb.updated_at = now_utc()
        await update_task_state(session, task, status="completed", stage="completed", progress=100)
    except asyncio.CancelledError:
        trace_level = "ERROR"
        trace_status_message = "Wiki 任务被 worker 取消或超时"
        await mark_wiki_task_failed(
            session,
            task_id=task_id,
            code="wiki_ingest_cancelled",
            message=trace_status_message,
        )
        raise
    except Exception as exc:
        trace_level = "ERROR"
        trace_status_message = str(exc)
        await mark_wiki_task_failed(
            session,
            task_id=task_id,
            code=getattr(exc, "code", "wiki_ingest_failed"),
            message=str(exc),
        )
        raise
    finally:
        trace.finish(level=trace_level, status_message=trace_status_message)


async def mark_wiki_task_failed(
    session: AsyncSession,
    *,
    task_id: str,
    code: str,
    message: str,
) -> None:
    await session.rollback()
    task = await session.get(TaskPendingOp, task_id)
    kb = await session.get(KnowledgeBase, task.kb_id) if task is not None else None
    if kb is not None:
        kb.status = "active"
        kb.updated_at = now_utc()
    if task is not None:
        task.status = "failed"
        task.stage = "failed"
        task.progress = 100
        task.error = {"code": code, "message": message}
        task.updated_at = now_utc()
    await session.commit()


async def update_task_state(
    session: AsyncSession,
    task: TaskPendingOp,
    *,
    status: str,
    stage: str,
    progress: int,
) -> None:
    task.status = status
    task.stage = stage
    task.progress = progress
    task.updated_at = now_utc()
    await session.commit()


class ObservedLLMProvider(LLMProvider):
    def __init__(self, delegate: LLMProvider, trace: Any) -> None:
        self.delegate = delegate
        self.trace = trace

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        stage = (prompt_metadata or {}).get("prompt_stage") or stage_from_messages(messages)
        metadata = {
            "stage": stage,
            "temperature": temperature,
            "timeout_seconds": timeout_seconds,
        }
        if prompt_metadata:
            metadata.update(prompt_metadata)
        with self.trace.span(
            name=f"llm_{stage}",
            metadata=metadata,
        ) as span:
            response = await self.delegate.complete(
                messages,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                prompt_metadata=prompt_metadata,
            )
            span.update(input=messages, output=response)
            return response


def stage_from_messages(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        content = message.get("content", "")
        match = re.search(r"<stage>([^<]+)</stage>", content)
        if match:
            return normalize_slug(match.group(1)).replace("/", "_") or "call"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue
        stage = parsed.get("stage") if isinstance(parsed, dict) else None
        if isinstance(stage, str) and stage:
            return normalize_slug(stage).replace("/", "_") or "call"
    return "call"


async def source_documents_for_task(
    session: AsyncSession,
    *,
    kb: KnowledgeBase,
    document_ids: list[str],
) -> list[Document]:
    source_ids = list(
        (
            await session.execute(
                select(WikiSourceBinding.source_kb_id).where(WikiSourceBinding.wiki_kb_id == kb.id)
            )
        ).scalars()
    )
    if not source_ids:
        raise ApiError("validation_error", "Wiki KB 尚未绑定 Source KB", 422)
    conditions: list[Any] = [Document.kb_id.in_(source_ids), Document.status == "completed"]
    if document_ids:
        conditions.append(Document.id.in_(document_ids))
    result = await session.execute(select(Document).where(*conditions).order_by(Document.created_at))
    documents = list(result.scalars())
    if document_ids and len(documents) != len(set(document_ids)):
        raise ApiError("validation_error", "存在不可摄入的文档", 422)
    return documents


async def chunks_for_documents(session: AsyncSession, document_ids: list[str]) -> dict[str, list[Chunk]]:
    result = await session.execute(
        select(Chunk)
        .where(Chunk.document_id.in_(document_ids), Chunk.chunk_type == "text")
        .order_by(Chunk.document_id, Chunk.seq)
    )
    grouped: dict[str, list[Chunk]] = {document_id: [] for document_id in document_ids}
    for chunk in result.scalars():
        if chunk.document_id:
            grouped.setdefault(chunk.document_id, []).append(chunk)
    return grouped


async def extract_candidates(
    llm: LLMProvider | None,
    *,
    documents: list[Document],
    chunks_by_doc: dict[str, list[Chunk]],
    existing_slugs: list[str],
    config: WikiConfig,
) -> list[WikiCandidate]:
    candidates: dict[str, WikiCandidate] = {}
    for document in documents:
        chunks = chunks_by_doc.get(document.id, [])
        llm_items = await llm_extract(llm, document=document, chunks=chunks, existing_slugs=existing_slugs, config=config)
        for item in llm_items or fallback_candidates(document, chunks):
            candidate = normalize_candidate(item, document.id)
            if candidate.slug not in candidates:
                candidates[candidate.slug] = candidate
            else:
                current = candidates[candidate.slug]
                candidates[candidate.slug] = WikiCandidate(
                    name=current.name,
                    slug=current.slug,
                    page_type=current.page_type,
                    entity_type=current.entity_type,
                    aliases=sorted(set(current.aliases + candidate.aliases)),
                    description=current.description or candidate.description,
                    source_refs=sorted(set(current.source_refs + candidate.source_refs)),
                )
            if len(candidates) >= MAX_CANDIDATES:
                break
    if not candidates:
        raise ApiError("wiki_no_candidates", "未能从文档中抽取 Wiki 条目", 409)
    return list(candidates.values())


async def cite_candidates(
    llm: LLMProvider | None,
    *,
    candidates: list[WikiCandidate],
    chunks_by_doc: dict[str, list[Chunk]],
    config: WikiConfig,
) -> dict[str, list[str]]:
    all_chunks = [chunk for chunks in chunks_by_doc.values() for chunk in chunks]
    by_id = {chunk.id: chunk for chunk in all_chunks}
    llm_citations = await llm_citation(llm, candidates=candidates, chunks=all_chunks, config=config)
    result: dict[str, list[str]] = {}
    for candidate in candidates:
        chunk_ids = [chunk_id for chunk_id in llm_citations.get(candidate.slug, []) if chunk_id in by_id]
        if not chunk_ids:
            names = [candidate.name, *candidate.aliases]
            chunk_ids = [
                chunk.id
                for chunk in all_chunks
                if any(name and name.lower() in chunk.content.lower() for name in names)
            ][:6]
        if not chunk_ids:
            chunk_ids = [chunk.id for chunk in all_chunks[:3]]
        result[candidate.slug] = chunk_ids
    return result


async def plan_taxonomy(
    llm: LLMProvider | None,
    *,
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> dict[str, list[str]]:
    planned = await llm_taxonomy(llm, candidates=candidates, config=config)
    taxonomy: dict[str, list[str]] = {}
    for candidate in candidates:
        path = planned.get(candidate.slug) or fallback_category(candidate)
        taxonomy[candidate.slug] = [str(item)[:32] for item in path[:2] if str(item).strip()] or ["未分类"]
    return taxonomy


async def write_source_pages(
    session: AsyncSession,
    llm: LLMProvider | None,
    *,
    kb: KnowledgeBase,
    documents: list[Document],
    chunks_by_doc: dict[str, list[Chunk]],
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> None:
    for document in documents:
        markdown = await llm_source_summary(llm, document=document, chunks=chunks_by_doc.get(document.id, []), candidates=candidates, config=config)
        if not markdown:
            markdown = fallback_source_summary(document, chunks_by_doc.get(document.id, []), candidates)
        await upsert_wiki_page(
            session,
            kb_id=kb.id,
            slug=f"source/{document.id}",
            title=document.filename,
            page_type="source",
            markdown=markdown,
            category_path=["来源"],
            aliases=[document.filename],
            source_refs=[document.id],
            change_summary="生成来源摘要页",
        )
        await session.commit()


async def write_candidate_pages(
    session: AsyncSession,
    llm: LLMProvider | None,
    *,
    kb: KnowledgeBase,
    candidates: list[WikiCandidate],
    citations: dict[str, list[str]],
    taxonomy: dict[str, list[str]],
    chunks_by_doc: dict[str, list[Chunk]],
    config: WikiConfig,
) -> None:
    chunk_lookup = {
        chunk.id: chunk
        for chunks in chunks_by_doc.values()
        for chunk in chunks
    }
    entities_by_slug: dict[str, Entity] = {}
    for candidate in candidates:
        source_chunks = [chunk_lookup[chunk_id] for chunk_id in citations.get(candidate.slug, []) if chunk_id in chunk_lookup]
        markdown, relations = await llm_reduce(llm, candidate=candidate, candidates=candidates, chunks=source_chunks, config=config)
        if not markdown:
            markdown = fallback_candidate_markdown(candidate, candidates, source_chunks)
        page = await upsert_wiki_page(
            session,
            kb_id=kb.id,
            slug=candidate.slug,
            title=candidate.name,
            page_type=candidate.page_type,
            markdown=markdown,
            category_path=taxonomy[candidate.slug],
            aliases=candidate.aliases,
            source_refs=candidate.source_refs,
            change_summary=f"归并 {candidate.name}",
        )
        entity = await upsert_entity(
            session,
            kb_id=kb.id,
            slug=candidate.slug,
            name=candidate.name,
            entity_type=candidate.entity_type,
            description=candidate.description or page.summary,
            aliases=candidate.aliases,
            wiki_page_id=page.id,
        )
        entities_by_slug[candidate.slug] = entity
        await session.commit()

        relation_items = relations or fallback_relations(candidate, candidates)
        for item in relation_items:
            target_slug = normalize_slug(str(item.get("target_slug") or ""))
            if not target_slug or target_slug == candidate.slug:
                continue
            target = next((candidate_item for candidate_item in candidates if candidate_item.slug == target_slug), None)
            if target is None:
                continue
            target_entity = entities_by_slug.get(target.slug)
            if target_entity is None:
                target_entity = await upsert_entity(
                    session,
                    kb_id=kb.id,
                    slug=target.slug,
                    name=target.name,
                    entity_type=target.entity_type,
                    description=target.description,
                    aliases=target.aliases,
                    wiki_page_id=None,
                )
                entities_by_slug[target.slug] = target_entity
            await upsert_relation(
                session,
                kb_id=kb.id,
                source_entity_id=entity.id,
                target_entity_id=target_entity.id,
                relation_type=str(item.get("relation_type") or "相关")[:64],
                source_chunk_id=source_chunks[0].id if source_chunks else None,
            )
        await session.commit()


async def write_postprocess_pages(
    session: AsyncSession,
    llm: LLMProvider | None,
    *,
    kb: KnowledgeBase,
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> None:
    pages = list((await session.execute(select(WikiPage).where(WikiPage.kb_id == kb.id))).scalars())
    known_slugs = {page.slug for page in pages} | {candidate.slug for candidate in candidates}
    for page in pages:
        cleaned = clean_dead_links(page.content, known_slugs)
        if cleaned != page.content:
            await upsert_wiki_page(
                session,
                kb_id=kb.id,
                slug=page.slug,
                title=page.title,
                page_type=page.page_type,
                markdown=full_markdown(page.summary, cleaned),
                category_path=page.category_path,
                aliases=page.aliases,
                source_refs=page.source_refs,
                change_summary="清理死链",
            )
            await session.commit()

    overview = await llm_overview(llm, pages=pages, candidates=candidates, config=config)
    if not overview:
        overview = fallback_overview(candidates)
    await upsert_wiki_page(
        session,
        kb_id=kb.id,
        slug="overview",
        title="全局综述",
        page_type="overview",
        markdown=overview,
        category_path=["综述"],
        aliases=["全局综述"],
        source_refs=sorted({ref for candidate in candidates for ref in candidate.source_refs}),
        change_summary="更新全局综述",
    )
    await upsert_wiki_page(
        session,
        kb_id=kb.id,
        slug="analysis/cross-document",
        title="跨文档分析",
        page_type="analysis",
        markdown=fallback_analysis(candidates),
        category_path=["分析"],
        aliases=["跨文档分析"],
        source_refs=sorted({ref for candidate in candidates for ref in candidate.source_refs}),
        change_summary="更新跨文档分析",
    )
    await upsert_wiki_page(
        session,
        kb_id=kb.id,
        slug="index",
        title="索引",
        page_type="index",
        markdown=fallback_index(candidates),
        category_path=["索引"],
        aliases=["首页", "目录"],
        source_refs=[],
        change_summary="更新索引页",
    )
    await session.commit()


async def embed_wiki_pages(
    session: AsyncSession,
    *,
    settings: Settings,
    ollama_client: OllamaClient,
    kb: KnowledgeBase,
) -> None:
    row = await get_or_create_settings(session, settings)
    pages = list((await session.execute(select(WikiPage).where(WikiPage.kb_id == kb.id))).scalars())
    provider = OllamaEmbeddingProvider(
        client=ollama_client,
        base_url=row.ollama_base_url,
        tag=kb.embedding_model_tag,
    )
    inputs = [f"{page.title}\n{full_markdown(page.summary, page.content)}" for page in pages]
    embeddings = await provider.embed(inputs)
    for embedding in embeddings:
        if len(embedding) != kb.embedding_dim:
            raise ApiError("embedding_incompatible", "Embedding 维度与知识库不匹配", 409)
    await index_wiki_pages(session, kb=kb, embeddings=embeddings)
    await session.commit()


async def llm_json(
    llm: LLMProvider | None,
    *,
    prompt: WikiPrompt,
    config: WikiConfig,
) -> dict[str, Any] | None:
    if llm is None:
        return None
    response = await llm.complete(
        [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
        temperature=config.temperature,
        timeout_seconds=config.llm_timeout_seconds,
        prompt_metadata=prompt.metadata,
    )
    return parse_json_object(response)


async def llm_markdown(
    llm: LLMProvider | None,
    *,
    prompt: WikiPrompt,
    config: WikiConfig,
) -> str | None:
    if llm is None:
        return None
    return await llm.complete(
        [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
        temperature=config.temperature,
        timeout_seconds=config.llm_timeout_seconds,
        prompt_metadata=prompt.metadata,
    )


async def llm_extract(
    llm: LLMProvider | None,
    *,
    document: Document,
    chunks: list[Chunk],
    existing_slugs: list[str],
    config: WikiConfig,
) -> list[dict[str, Any]] | None:
    prompt = build_extract_prompt(
        document_id=document.id,
        existing_slugs=existing_slugs,
        chunks=chunk_payload(chunks[:20]),
        extraction_granularity="standard",
        custom_instructions="",
    )
    payload = await llm_json(
        llm,
        prompt=prompt,
        config=config,
    )
    items = payload.get("candidates") if payload else None
    return items if isinstance(items, list) else None


async def llm_citation(
    llm: LLMProvider | None,
    *,
    candidates: list[WikiCandidate],
    chunks: list[Chunk],
    config: WikiConfig,
) -> dict[str, list[str]]:
    prompt = build_citation_prompt(
        candidates=[candidate_payload(item) for item in candidates],
        chunks=chunk_payload(chunks[:80]),
    )
    payload = await llm_json(
        llm,
        prompt=prompt,
        config=config,
    )
    result: dict[str, list[str]] = {}
    items = payload.get("citations") if payload else None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("chunk_ids"), list):
                result[normalize_slug(str(item.get("slug") or ""))] = [str(chunk_id) for chunk_id in item["chunk_ids"]]
    return result


async def llm_taxonomy(
    llm: LLMProvider | None,
    *,
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> dict[str, list[str]]:
    prompt = build_taxonomy_prompt(candidates=[candidate_payload(item) for item in candidates])
    payload = await llm_json(
        llm,
        prompt=prompt,
        config=config,
    )
    result: dict[str, list[str]] = {}
    items = payload.get("items") if payload else None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("category_path"), list):
                result[normalize_slug(str(item.get("slug") or ""))] = [str(path) for path in item["category_path"]]
    return result


async def llm_source_summary(
    llm: LLMProvider | None,
    *,
    document: Document,
    chunks: list[Chunk],
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> str | None:
    prompt = build_source_summary_prompt(
        document_id=document.id,
        allowed_links=[candidate_payload(item) for item in candidates],
        chunks=chunk_payload(chunks[:20]),
    )
    return await llm_markdown(
        llm,
        prompt=prompt,
        config=config,
    )


async def llm_reduce(
    llm: LLMProvider | None,
    *,
    candidate: WikiCandidate,
    candidates: list[WikiCandidate],
    chunks: list[Chunk],
    config: WikiConfig,
) -> tuple[str | None, list[dict[str, Any]]]:
    prompt = build_reduce_prompt(
        candidate=candidate_payload(candidate),
        allowed_links=[candidate_payload(item) for item in candidates],
        chunks=chunk_payload(chunks[:16]),
        existing_page_markdown="",
    )
    payload = await llm_json(
        llm,
        prompt=prompt,
        config=config,
    )
    if not payload:
        return None, []
    content = payload.get("content")
    relations = payload.get("relations")
    return (content if isinstance(content, str) else None), (relations if isinstance(relations, list) else [])


async def llm_overview(
    llm: LLMProvider | None,
    *,
    pages: list[WikiPage],
    candidates: list[WikiCandidate],
    config: WikiConfig,
) -> str | None:
    prompt = build_overview_prompt(
        allowed_links=[candidate_payload(item) for item in candidates],
        page_summaries=[
            {"slug": page.slug, "title": page.title, "summary": page.summary}
            for page in pages[:40]
        ],
    )
    return await llm_markdown(
        llm,
        prompt=prompt,
        config=config,
    )


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def chunk_payload(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [
        {
            "id": chunk.id,
            "header_path": chunk.header_path,
            "content": chunk.content[:1200],
        }
        for chunk in chunks
    ]


def candidate_payload(candidate: WikiCandidate) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "slug": candidate.slug,
        "page_type": candidate.page_type,
        "entity_type": candidate.entity_type,
        "aliases": candidate.aliases,
        "description": candidate.description,
    }


def normalize_candidate(item: dict[str, Any], document_id: str) -> WikiCandidate:
    name = str(item.get("name") or "").strip()[:120] or "未命名条目"
    page_type = str(item.get("page_type") or "concept")
    if page_type not in {"entity", "concept"}:
        page_type = "concept"
    entity_type = str(item.get("entity_type") or ("tech" if page_type == "concept" else "other"))[:32]
    slug = normalize_slug(str(item.get("slug") or ""))
    if not slug:
        slug = f"{page_type}/{slug_tail(name)}"
    if "/" not in slug:
        slug = f"{page_type}/{slug}"
    aliases = item.get("aliases")
    aliases_list = [str(alias).strip()[:120] for alias in aliases if str(alias).strip()] if isinstance(aliases, list) else []
    return WikiCandidate(
        name=name,
        slug=slug,
        page_type=page_type,
        entity_type=entity_type,
        aliases=sorted(set([name, *aliases_list])),
        description=str(item.get("description") or name).strip()[:500],
        source_refs=[document_id],
    )


def normalize_slug(value: str) -> str:
    value = value.strip().lower().replace("\\", "/")
    value = re.sub(r"[^a-z0-9/_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-/")
    return value


def slug_tail(value: str) -> str:
    ascii_tail = normalize_slug(value)
    if ascii_tail:
        return ascii_tail[:80]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"item-{digest}"


def fallback_candidates(document: Document, chunks: list[Chunk]) -> list[dict[str, Any]]:
    names: list[str] = []
    for chunk in chunks:
        for title in chunk.header_path:
            if title and title not in names:
                names.append(title)
        for match in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", chunk.content):
            if match not in names:
                names.append(match)
        if len(names) >= 6:
            break
    if not names:
        names = [document.filename.rsplit(".", 1)[0]]
    items: list[dict[str, Any]] = []
    for index, name in enumerate(names[:6]):
        page_type = "entity" if index == 0 else "concept"
        items.append(
            {
                "name": name,
                "slug": f"{page_type}/{slug_tail(name)}",
                "page_type": page_type,
                "entity_type": "tech" if page_type == "concept" else "other",
                "aliases": [name],
                "description": f"{name} 是从 {document.filename} 抽取的 Wiki 条目。",
            }
        )
    return items


def fallback_category(candidate: WikiCandidate) -> list[str]:
    if candidate.page_type == "entity":
        return ["实体", candidate.entity_type or "other"]
    return ["概念", "知识条目"]


def fallback_source_summary(document: Document, chunks: list[Chunk], candidates: list[WikiCandidate]) -> str:
    links = ", ".join(f"[[{candidate.slug}|{candidate.name}]]" for candidate in candidates[:6])
    excerpt = chunks[0].content[:400] if chunks else ""
    return (
        f"SUMMARY: {document.filename} 的来源摘要。\n\n"
        "## 关键要点\n\n"
        f"- 来源文档包含 {len(chunks)} 个可检索 chunk。\n"
        f"- 关联条目：{links or '暂无'}。\n\n"
        "## 摘要\n\n"
        f"{excerpt}"
    )


def fallback_candidate_markdown(candidate: WikiCandidate, candidates: list[WikiCandidate], chunks: list[Chunk]) -> str:
    related = [item for item in candidates if item.slug != candidate.slug][:4]
    links = ", ".join(f"[[{item.slug}|{item.name}]]" for item in related)
    evidence = "\n".join(f"- {chunk.content[:240]}" for chunk in chunks[:4])
    return (
        f"SUMMARY: {candidate.description}\n\n"
        "## 概览\n\n"
        f"{candidate.description}\n\n"
        "## 相关条目\n\n"
        f"{links or '暂无关联条目'}\n\n"
        "## 来源证据\n\n"
        f"{evidence or '- 暂无可用证据'}"
    )


def fallback_relations(candidate: WikiCandidate, candidates: list[WikiCandidate]) -> list[dict[str, Any]]:
    for item in candidates:
        if item.slug != candidate.slug:
            return [{"target_slug": item.slug, "relation_type": "相关"}]
    return []


def fallback_overview(candidates: list[WikiCandidate]) -> str:
    lines = "\n".join(f"- [[{candidate.slug}|{candidate.name}]]：{candidate.description}" for candidate in candidates)
    return f"SUMMARY: 当前 Wiki 覆盖 {len(candidates)} 个核心条目。\n\n## 核心条目\n\n{lines}"


def fallback_analysis(candidates: list[WikiCandidate]) -> str:
    entity_count = sum(1 for candidate in candidates if candidate.page_type == "entity")
    concept_count = sum(1 for candidate in candidates if candidate.page_type == "concept")
    return (
        f"SUMMARY: 当前 Wiki 包含 {entity_count} 个实体和 {concept_count} 个概念，可用于跨文档浏览。\n\n"
        "## 覆盖情况\n\n"
        f"- 实体页：{entity_count}\n"
        f"- 概念页：{concept_count}\n\n"
        "## 后续关注\n\n"
        "- 若来源文档存在冲突事实，后续可在 M5 编辑与版本能力中人工校正。"
    )


def fallback_index(candidates: list[WikiCandidate]) -> str:
    groups: dict[str, list[WikiCandidate]] = {"实体": [], "概念": []}
    for candidate in candidates:
        groups["实体" if candidate.page_type == "entity" else "概念"].append(candidate)
    sections = []
    for title, items in groups.items():
        if not items:
            continue
        links = "\n".join(f"- [[{item.slug}|{item.name}]]" for item in items)
        sections.append(f"## {title}\n\n{links}")
    body = "\n\n".join(sections)
    return f"SUMMARY: Wiki 索引页，按页面类型组织主要条目。\n\n{body}"


def clean_dead_links(content: str, known_slugs: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        slug = normalize_slug(match.group(1))
        label = match.group(2)
        return match.group(0) if slug in known_slugs else label

    return re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", replace, content)
