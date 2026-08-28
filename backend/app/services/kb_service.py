from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import Document, KnowledgeBase, WikiPage, WikiSourceBinding
from app.schemas import (
    ChunkingConfig,
    KnowledgeBaseOut,
    KnowledgeBasePage,
    KnowledgeBaseSummary,
    WikiConfig,
    WikiSourceBindingOut,
)
from app.services.audit_service import record_audit
from app.services.model_service import OllamaClient, get_or_create_settings, probe_ollama_model


def default_chunking() -> dict[str, Any]:
    return ChunkingConfig().model_dump()


def default_wiki_config() -> dict[str, Any]:
    return WikiConfig().model_dump()


def kb_summary(kb: KnowledgeBase) -> KnowledgeBaseSummary:
    return KnowledgeBaseSummary(id=kb.id, name=kb.name, type=kb.type, status=kb.status)


async def bound_sources(session: AsyncSession, kb: KnowledgeBase) -> list[KnowledgeBaseSummary]:
    if kb.type != "wiki":
        return []
    result = await session.execute(
        select(KnowledgeBase)
        .join(WikiSourceBinding, WikiSourceBinding.source_kb_id == KnowledgeBase.id)
        .where(WikiSourceBinding.wiki_kb_id == kb.id)
        .order_by(KnowledgeBase.created_at)
    )
    return [kb_summary(source) for source in result.scalars()]


async def kb_out(session: AsyncSession, kb: KnowledgeBase) -> KnowledgeBaseOut:
    document_count = 0
    page_count = 0
    if kb.type == "document":
        document_count = int(
            await session.scalar(select(func.count()).select_from(Document).where(Document.kb_id == kb.id))
            or 0
        )
    if kb.type == "wiki":
        page_count = int(
            await session.scalar(select(func.count()).select_from(WikiPage).where(WikiPage.kb_id == kb.id))
            or 0
        )
    return KnowledgeBaseOut(
        id=kb.id,
        workspace_id=kb.workspace_id,
        name=kb.name,
        description=kb.description,
        type=kb.type,
        status=kb.status,
        embedding_provider="ollama",
        embedding_model_tag=kb.embedding_model_tag,
        embedding_model_digest=kb.embedding_model_digest,
        embedding_dim=1024,
        chunking_config=ChunkingConfig.model_validate(kb.chunking_config)
        if kb.chunking_config
        else None,
        wiki_config=WikiConfig.model_validate(kb.wiki_config) if kb.wiki_config else None,
        document_count=document_count,
        page_count=page_count,
        bound_source_kbs=await bound_sources(session, kb),
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


async def list_kbs(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_type: str | None,
    status: str | None,
    q: str | None,
    page: int,
    page_size: int,
) -> KnowledgeBasePage:
    conditions = [KnowledgeBase.workspace_id == workspace_id]
    if kb_type:
        conditions.append(KnowledgeBase.type == kb_type)
    if status:
        conditions.append(KnowledgeBase.status == status)
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                KnowledgeBase.name.ilike(like),
                KnowledgeBase.description.ilike(like),
            )
        )

    total = await session.scalar(select(func.count()).select_from(KnowledgeBase).where(*conditions))
    result = await session.execute(
        select(KnowledgeBase)
        .where(*conditions)
        .order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [await kb_out(session, kb) for kb in result.scalars()]
    return KnowledgeBasePage(items=items, total=int(total or 0), page=page, page_size=page_size)


async def get_kb(session: AsyncSession, *, workspace_id: str, kb_id: str) -> KnowledgeBase:
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if kb is None:
        raise ApiError("not_found", "知识库不存在", 404)
    return kb


async def require_usable_embedding(
    session: AsyncSession,
    *,
    settings: Settings,
    tag: str,
    client: OllamaClient,
) -> tuple[str, int]:
    row = await get_or_create_settings(session, settings)
    probe = await probe_ollama_model(base_url=row.ollama_base_url, tag=tag, client=client)
    if not probe.usable_for_v1:
        code = (
            "embedding_dimension_incompatible"
            if probe.unusable_reason == "dimension_incompatible"
            else "embedding_model_invalid"
        )
        raise ApiError(code, "Embedding 模型不可用于 v1", 422, details=probe.model_dump())
    return probe.digest, 1024


async def validate_source_ids(
    session: AsyncSession,
    *,
    workspace_id: str,
    source_ids: list[str],
) -> list[KnowledgeBase]:
    result = await session.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.workspace_id == workspace_id,
            KnowledgeBase.type == "document",
            KnowledgeBase.id.in_(source_ids),
        )
    )
    sources = list(result.scalars())
    if len(sources) != len(set(source_ids)):
        raise ApiError("validation_error", "绑定的 Source KB 不存在", 422)
    return sources


async def create_kb(
    session: AsyncSession,
    *,
    settings: Settings,
    client: OllamaClient,
    workspace_id: str,
    actor_id: str,
    payload: dict[str, Any],
) -> KnowledgeBaseOut:
    digest, dim = await require_usable_embedding(
        session,
        settings=settings,
        tag=str(payload["embedding_model_tag"]),
        client=client,
    )
    kb_type = str(payload["type"])
    source_ids = [str(item) for item in payload.get("source_knowledge_base_ids", [])]
    if kb_type == "wiki":
        await validate_source_ids(session, workspace_id=workspace_id, source_ids=source_ids)

    kb = KnowledgeBase(
        workspace_id=workspace_id,
        name=str(payload["name"]),
        description=str(payload.get("description") or ""),
        type=kb_type,
        status="active",
        embedding_provider="ollama",
        embedding_model_tag=str(payload["embedding_model_tag"]),
        embedding_model_digest=digest,
        embedding_dim=dim,
        chunking_config=(payload.get("chunking_config") or default_chunking())
        if kb_type == "document"
        else None,
        wiki_config=(payload.get("wiki_config") or default_wiki_config())
        if kb_type == "wiki"
        else None,
    )
    session.add(kb)
    await session.flush()
    for source_id in source_ids:
        session.add(WikiSourceBinding(wiki_kb_id=kb.id, source_kb_id=source_id))
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="kb.create",
        resource_type="kb",
        resource_id=kb.id,
        details={"type": kb_type, "name": kb.name},
    )
    await session.commit()
    return await kb_out(session, kb)


async def update_kb(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    payload: dict[str, Any],
) -> KnowledgeBaseOut:
    kb = await get_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    if payload.get("name") is not None:
        kb.name = str(payload["name"])
    if payload.get("description") is not None:
        kb.description = str(payload["description"])
    if payload.get("status") is not None:
        kb.status = str(payload["status"])
    if payload.get("chunking_config") is not None:
        if kb.type != "document":
            raise ApiError("validation_error", "只有 Source KB 可修改分块配置", 422)
        kb.chunking_config = payload["chunking_config"]
    if payload.get("wiki_config") is not None:
        if kb.type != "wiki":
            raise ApiError("validation_error", "只有 Wiki KB 可修改 Wiki 配置", 422)
        kb.wiki_config = payload["wiki_config"]
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="kb.update",
        resource_type="kb",
        resource_id=kb.id,
        details=payload,
    )
    await session.commit()
    return await kb_out(session, kb)


async def delete_kb(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
) -> None:
    kb = await get_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    await session.execute(
        delete(WikiSourceBinding).where(
            or_(
                WikiSourceBinding.wiki_kb_id == kb.id,
                WikiSourceBinding.source_kb_id == kb.id,
            )
        )
    )
    await session.delete(kb)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="kb.delete",
        resource_type="kb",
        resource_id=kb_id,
    )
    await session.commit()


async def bind_source(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    wiki_kb_id: str,
    source_kb_id: str,
) -> WikiSourceBindingOut:
    wiki = await get_kb(session, workspace_id=workspace_id, kb_id=wiki_kb_id)
    if wiki.type != "wiki":
        raise ApiError("validation_error", "只能为 Wiki KB 绑定 Source KB", 422)
    await validate_source_ids(session, workspace_id=workspace_id, source_ids=[source_kb_id])
    existing = await session.scalar(
        select(WikiSourceBinding).where(
            WikiSourceBinding.wiki_kb_id == wiki_kb_id,
            WikiSourceBinding.source_kb_id == source_kb_id,
        )
    )
    if existing is not None:
        raise ApiError("conflict", "绑定已存在", 409)
    binding = WikiSourceBinding(wiki_kb_id=wiki_kb_id, source_kb_id=source_kb_id)
    session.add(binding)
    await session.flush()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="kb.bind_source",
        resource_type="kb",
        resource_id=wiki_kb_id,
        details={"source_kb_id": source_kb_id},
    )
    await session.commit()
    return WikiSourceBindingOut(
        id=binding.id,
        wiki_kb_id=binding.wiki_kb_id,
        source_kb_id=binding.source_kb_id,
        created_at=binding.created_at,
    )


async def unbind_source(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    wiki_kb_id: str,
    source_kb_id: str,
) -> None:
    await get_kb(session, workspace_id=workspace_id, kb_id=wiki_kb_id)
    binding = await session.scalar(
        select(WikiSourceBinding).where(
            WikiSourceBinding.wiki_kb_id == wiki_kb_id,
            WikiSourceBinding.source_kb_id == source_kb_id,
        )
    )
    if binding is None:
        raise ApiError("not_found", "绑定不存在", 404)
    await session.delete(binding)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="kb.unbind_source",
        resource_type="kb",
        resource_id=wiki_kb_id,
        details={"source_kb_id": source_kb_id},
    )
    await session.commit()
