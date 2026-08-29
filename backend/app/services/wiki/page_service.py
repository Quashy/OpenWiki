import json
import re
from typing import Any

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import Chunk, Document, Entity, KnowledgeBase, Relation, WikiPage, WikiPageRevision
from app.models.m1 import new_uuid, now_utc
from app.schemas import (
    WikiGraph,
    WikiGraphEdge,
    WikiGraphNode,
    WikiPageListResponse,
    WikiPageOut,
    WikiPageSource,
    WikiPageSourceChunk,
    WikiPageSourceResponse,
    WikiPageSummary,
    WikiPageTreeNode,
)
from app.services.retrieval.dense import vector_literal

DOUBLE_LINK_RE = re.compile(r"\[\[([^|\]]+)\|([^\]]+)\]\]")


async def require_wiki_kb(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
    require_queryable: bool = False,
) -> KnowledgeBase:
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if kb is None:
        raise ApiError("not_found", "知识库不存在", 404)
    if kb.type != "wiki":
        raise ApiError("validation_error", "只能操作 Wiki KB", 422)
    if require_queryable and kb.status == "building":
        raise ApiError("kb_unavailable", "Wiki 正在重建中", 409)
    if require_queryable and kb.status == "embedding_incompatible":
        raise ApiError("embedding_incompatible", "Embedding 模型不兼容", 409)
    return kb


def split_summary_line(markdown: str) -> tuple[str, str]:
    lines = markdown.strip().splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if first.startswith("SUMMARY:"):
        summary = first.removeprefix("SUMMARY:").strip()
        content = "\n".join(lines[1:]).strip()
        return summary, content
    return first[:200], markdown.strip()


def full_markdown(summary: str, content: str) -> str:
    return f"SUMMARY: {summary.strip()}\n\n{content.strip()}".strip()


def page_summary(page: WikiPage) -> WikiPageSummary:
    return WikiPageSummary(
        id=page.id,
        kb_id=page.kb_id,
        slug=page.slug,
        title=page.title,
        page_type=page.page_type,
        summary=page.summary,
        category_path=list(page.category_path or []),
        aliases=list(page.aliases or []),
        source_refs=list(page.source_refs or []),
        updated_at=page.updated_at,
    )


def page_out(page: WikiPage) -> WikiPageOut:
    if page.current_revision_id is None:
        raise ApiError("wiki_page_invalid", "Wiki 页面缺少当前修订", 500)
    return WikiPageOut(
        **page_summary(page).model_dump(),
        content=page.content,
        current_revision_id=page.current_revision_id,
        manual_edit_warning=False,
        created_at=page.created_at,
    )


async def get_wiki_page_sources(
    session: AsyncSession,
    *,
    workspace_id: str,
    page_id: str,
) -> WikiPageSourceResponse:
    page = await session.scalar(
        select(WikiPage)
        .join(KnowledgeBase, KnowledgeBase.id == WikiPage.kb_id)
        .where(WikiPage.id == page_id, KnowledgeBase.workspace_id == workspace_id)
    )
    if page is None:
        raise ApiError("not_found", "Wiki 页面不存在", 404)

    citations_by_doc = normalized_source_citations(page.source_citations or [])
    source_ref_ids = [str(item) for item in page.source_refs or []]
    document_ids = sorted(set(source_ref_ids) | set(citations_by_doc))
    if not document_ids:
        return WikiPageSourceResponse(items=[])

    documents = list(
        (
            await session.execute(
                select(Document)
                .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
                .where(Document.id.in_(document_ids), KnowledgeBase.workspace_id == workspace_id)
                .order_by(Document.filename)
            )
        ).scalars()
    )
    document_by_id = {document.id: document for document in documents}
    visible_document_ids = set(document_by_id)
    if not visible_document_ids:
        return WikiPageSourceResponse(items=[])

    precise_document_ids = {
        document_id
        for document_id, chunk_ids in citations_by_doc.items()
        if document_id in visible_document_ids and chunk_ids
    }
    fallback_document_ids = visible_document_ids - precise_document_ids
    precise_chunk_ids = {
        chunk_id
        for document_id, chunk_ids in citations_by_doc.items()
        if document_id in visible_document_ids
        for chunk_id in chunk_ids
    }
    chunk_filters = []
    if precise_chunk_ids:
        chunk_filters.append(Chunk.id.in_(precise_chunk_ids))
    if fallback_document_ids:
        chunk_filters.append(Chunk.document_id.in_(fallback_document_ids))
    if chunk_filters:
        chunk_query = (
            select(Chunk)
            .where(Chunk.document_id.in_(visible_document_ids), or_(*chunk_filters))
            .order_by(Chunk.document_id, Chunk.seq)
        )
        chunks = list((await session.execute(chunk_query)).scalars())
    else:
        chunks = []

    chunks_by_doc: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        if chunk.document_id:
            chunks_by_doc.setdefault(chunk.document_id, []).append(chunk)

    items: list[WikiPageSource] = []
    for document in documents:
        precise = document.id in citations_by_doc and bool(citations_by_doc[document.id])
        selected_chunks = chunks_by_doc.get(document.id, [])
        items.append(
            WikiPageSource(
                document_id=document.id,
                filename=document.filename,
                status=document.status,
                precise=precise,
                chunks=[
                    WikiPageSourceChunk(
                        id=chunk.id,
                        seq=chunk.seq,
                        header_path=list(chunk.header_path or []),
                        content=chunk.content,
                        start_pos=chunk.start_pos,
                        end_pos=chunk.end_pos,
                    )
                    for chunk in selected_chunks
                ],
            )
        )
    return WikiPageSourceResponse(items=items)


def normalized_source_citations(value: list[dict[str, Any]]) -> dict[str, list[str]]:
    citations: dict[str, list[str]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        document_id = item.get("document_id")
        chunk_ids = item.get("chunk_ids")
        if not document_id or not isinstance(chunk_ids, list):
            continue
        clean_chunk_ids = [str(chunk_id) for chunk_id in chunk_ids if chunk_id]
        if clean_chunk_ids:
            citations[str(document_id)] = clean_chunk_ids
    return citations


def build_tree(pages: list[WikiPageSummary]) -> list[WikiPageTreeNode]:
    roots: dict[str, WikiPageTreeNode] = {}

    def child_for(parent: WikiPageTreeNode, name: str, path: list[str]) -> WikiPageTreeNode:
        for child in parent.children:
            if child.name == name:
                return child
        child = WikiPageTreeNode(name=name, path=path, pages=[], children=[])
        parent.children.append(child)
        return child

    for page in pages:
        path = page.category_path or ["未分类"]
        root_name = path[0]
        root = roots.setdefault(
            root_name,
            WikiPageTreeNode(name=root_name, path=[root_name], pages=[], children=[]),
        )
        if len(path) == 1:
            root.pages.append(page)
        else:
            child_for(root, path[1], path[:2]).pages.append(page)
    return sorted(roots.values(), key=lambda item: item.name)


async def list_wiki_pages(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
    q: str | None = None,
    page_type: str | None = None,
) -> WikiPageListResponse:
    await require_wiki_kb(session, workspace_id=workspace_id, kb_id=kb_id, require_queryable=True)
    conditions: list[Any] = [WikiPage.kb_id == kb_id]
    if page_type:
        conditions.append(WikiPage.page_type == page_type)
    if q:
        like = f"%{q}%"
        conditions.append(
            (WikiPage.title.ilike(like))
            | (WikiPage.summary.ilike(like))
            | (WikiPage.content.ilike(like))
        )
    result = await session.execute(
        select(WikiPage).where(*conditions).order_by(WikiPage.category_path, WikiPage.title)
    )
    items = [page_summary(page) for page in result.scalars()]
    return WikiPageListResponse(items=items, tree=build_tree(items))


async def get_wiki_page(
    session: AsyncSession,
    *,
    workspace_id: str,
    page_id: str,
) -> WikiPageOut:
    page = await session.scalar(
        select(WikiPage)
        .join(KnowledgeBase, KnowledgeBase.id == WikiPage.kb_id)
        .where(WikiPage.id == page_id, KnowledgeBase.workspace_id == workspace_id)
    )
    if page is None:
        raise ApiError("not_found", "Wiki 页面不存在", 404)
    if await session.scalar(select(KnowledgeBase.status).where(KnowledgeBase.id == page.kb_id)) == "building":
        raise ApiError("kb_unavailable", "Wiki 正在重建中", 409)
    return page_out(page)


async def upsert_wiki_page(
    session: AsyncSession,
    *,
    kb_id: str,
    slug: str,
    title: str,
    page_type: str,
    markdown: str,
    category_path: list[str],
    aliases: list[str],
    source_refs: list[str],
    source_citations: list[dict[str, Any]] | None = None,
    editor_type: str = "agent",
    editor_id: str | None = None,
    change_summary: str = "Wiki ingest 更新",
) -> WikiPage:
    summary, content = split_summary_line(markdown)
    now = now_utc()
    page = await session.scalar(select(WikiPage).where(WikiPage.kb_id == kb_id, WikiPage.slug == slug))
    if page is None:
        page = WikiPage(
            kb_id=kb_id,
            slug=slug,
            title=title,
            page_type=page_type,
            summary=summary,
            content=content,
            category_path=category_path[:2],
            aliases=aliases,
            source_refs=source_refs,
            source_citations=source_citations or [],
            created_at=now,
            updated_at=now,
        )
        session.add(page)
        await session.flush()
    else:
        page.title = title
        page.page_type = page_type
        page.summary = summary
        page.content = content
        page.category_path = category_path[:2]
        page.aliases = aliases
        page.source_refs = source_refs
        if source_citations is not None:
            page.source_citations = source_citations
        page.updated_at = now

    revision = WikiPageRevision(
        page_id=page.id,
        content=full_markdown(page.summary, page.content),
        editor_type=editor_type,
        editor_id=editor_id,
        change_summary=change_summary,
        created_at=now,
    )
    session.add(revision)
    await session.flush()
    page.current_revision_id = revision.id
    await session.flush()
    return page


async def clear_wiki_content(session: AsyncSession, *, kb_id: str) -> None:
    page_ids = list((await session.execute(select(WikiPage.id).where(WikiPage.kb_id == kb_id))).scalars())
    if page_ids:
        await session.execute(delete(Chunk).where(Chunk.source_page_id.in_(page_ids)))
        await session.execute(delete(WikiPageRevision).where(WikiPageRevision.page_id.in_(page_ids)))
    await session.execute(delete(Relation).where(Relation.kb_id == kb_id))
    await session.execute(delete(Entity).where(Entity.kb_id == kb_id))
    await session.execute(delete(WikiPage).where(WikiPage.kb_id == kb_id))


async def upsert_entity(
    session: AsyncSession,
    *,
    kb_id: str,
    slug: str,
    name: str,
    entity_type: str,
    description: str,
    aliases: list[str],
    wiki_page_id: str | None,
) -> Entity:
    entity = await session.scalar(select(Entity).where(Entity.kb_id == kb_id, Entity.slug == slug))
    if entity is None:
        entity = Entity(
            kb_id=kb_id,
            slug=slug,
            name=name,
            entity_type=entity_type,
            description=description,
            aliases=aliases,
            wiki_page_id=wiki_page_id,
            created_at=now_utc(),
        )
        session.add(entity)
    else:
        entity.name = name
        entity.entity_type = entity_type
        entity.description = description
        entity.aliases = aliases
        entity.wiki_page_id = wiki_page_id
    await session.flush()
    return entity


async def upsert_relation(
    session: AsyncSession,
    *,
    kb_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    source_chunk_id: str | None,
) -> Relation:
    relation = await session.scalar(
        select(Relation).where(
            Relation.source_entity_id == source_entity_id,
            Relation.target_entity_id == target_entity_id,
            Relation.relation_type == relation_type,
        )
    )
    if relation is None:
        relation = Relation(
            kb_id=kb_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            source_chunk_id=source_chunk_id,
            created_at=now_utc(),
        )
        session.add(relation)
    elif source_chunk_id:
        relation.source_chunk_id = source_chunk_id
    await session.flush()
    return relation


async def index_wiki_pages(
    session: AsyncSession,
    *,
    kb: KnowledgeBase,
    embeddings: list[list[float]],
) -> None:
    pages = list((await session.execute(select(WikiPage).where(WikiPage.kb_id == kb.id))).scalars())
    page_ids = [page.id for page in pages]
    if page_ids:
        await session.execute(delete(Chunk).where(Chunk.source_page_id.in_(page_ids)))
    if not pages:
        return
    created_at = now_utc()
    rows = []
    for seq, (page, embedding) in enumerate(zip(pages, embeddings, strict=True)):
        content = full_markdown(page.summary, page.content)
        rows.append(
            {
                "id": new_uuid(),
                "document_id": None,
                "kb_id": kb.id,
                "content": content,
                "header_path": [page.title],
                "seq": seq,
                "start_pos": 0,
                "end_pos": len(content),
                "embedding": embedding,
                "search_text": f"{page.title} {' > '.join(page.category_path or [])} {content}".replace(
                    "\n",
                    " ",
                ),
                "chunk_type": "wiki_page",
                "source_page_id": page.id,
                "created_at": created_at,
            }
        )

    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(
            text(
                """
                INSERT INTO chunks (
                    id, document_id, kb_id, content, header_path, seq,
                    start_pos, end_pos, embedding, search_text, chunk_type,
                    source_page_id, created_at
                )
                VALUES (
                    :id, :document_id, :kb_id, :content, CAST(:header_path AS jsonb),
                    :seq, :start_pos, :end_pos, CAST(:embedding AS vector),
                    :search_text, :chunk_type, :source_page_id, :created_at
                )
                """
            ),
            [
                {
                    **row,
                    "header_path": json.dumps(row["header_path"], ensure_ascii=True),
                    "embedding": vector_literal(row["embedding"]),
                }
                for row in rows
            ],
        )
        return

    for row in rows:
        session.add(Chunk(**row))


async def wiki_page_count(session: AsyncSession, *, kb_id: str) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(WikiPage).where(WikiPage.kb_id == kb_id))
        or 0
    )


async def get_wiki_graph(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
    entity_type: str | None = None,
    relation_type: str | None = None,
) -> WikiGraph:
    await require_wiki_kb(session, workspace_id=workspace_id, kb_id=kb_id, require_queryable=True)
    entity_query = select(Entity).where(Entity.kb_id == kb_id)
    if entity_type:
        entity_query = entity_query.where(Entity.entity_type == entity_type)
    entities = list((await session.execute(entity_query.order_by(Entity.name))).scalars())
    entity_ids = {entity.id for entity in entities}
    relation_query = select(Relation).where(Relation.kb_id == kb_id)
    if entity_ids:
        relation_query = relation_query.where(
            Relation.source_entity_id.in_(entity_ids),
            Relation.target_entity_id.in_(entity_ids),
        )
    else:
        relation_query = relation_query.where(False)
    if relation_type:
        relation_query = relation_query.where(Relation.relation_type == relation_type)
    relations = list((await session.execute(relation_query)).scalars())
    return WikiGraph(
        nodes=[
            WikiGraphNode(
                id=entity.id,
                name=entity.name,
                slug=entity.slug,
                entity_type=entity.entity_type,
                wiki_page_id=entity.wiki_page_id,
            )
            for entity in entities
        ],
        edges=[
            WikiGraphEdge(
                id=relation.id,
                source_entity_id=relation.source_entity_id,
                target_entity_id=relation.target_entity_id,
                relation_type=relation.relation_type,
                source_chunk_id=relation.source_chunk_id,
            )
            for relation in relations
        ],
    )
