from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Entity, Relation
from app.services.retrieval.dense import RetrievalResult


def normalize_query(value: str) -> str:
    return value.casefold().strip()


def entity_matches(entity: Entity, query: str) -> bool:
    normalized = normalize_query(query)
    surfaces = [entity.name, entity.slug, *(entity.aliases or [])]
    return any(surface and normalize_query(surface) in normalized for surface in surfaces)


async def graph_search(
    session: AsyncSession,
    *,
    kb_id: str,
    query: str,
    top_k: int = 20,
) -> list[RetrievalResult]:
    entities = list((await session.execute(select(Entity).where(Entity.kb_id == kb_id))).scalars())
    matched_ids = {entity.id for entity in entities if entity_matches(entity, query)}
    if not matched_ids:
        return []

    relation_rows = list(
        (
            await session.execute(
                select(Relation).where(
                    Relation.kb_id == kb_id,
                    or_(
                        Relation.source_entity_id.in_(matched_ids),
                        Relation.target_entity_id.in_(matched_ids),
                    ),
                )
            )
        ).scalars()
    )
    expanded_ids = set(matched_ids)
    for relation in relation_rows:
        expanded_ids.add(relation.source_entity_id)
        expanded_ids.add(relation.target_entity_id)

    page_ids = [
        entity.wiki_page_id
        for entity in entities
        if entity.id in expanded_ids and entity.wiki_page_id is not None
    ]
    if not page_ids:
        return []

    chunks = list(
        (
            await session.execute(
                select(Chunk)
                .where(
                    Chunk.kb_id == kb_id,
                    Chunk.chunk_type == "wiki_page",
                    Chunk.source_page_id.in_(page_ids),
                )
                .order_by(Chunk.seq.asc(), Chunk.id.asc())
                .limit(top_k)
            )
        ).scalars()
    )
    return [
        RetrievalResult(
            chunk_id=chunk.id,
            kb_id=chunk.kb_id,
            content=chunk.content,
            header_path=chunk.header_path,
            document_id=chunk.document_id,
            chunk_type=chunk.chunk_type,
            source_page_id=chunk.source_page_id,
            score=1.0 / (index + 1),
        )
        for index, chunk in enumerate(chunks)
    ]
