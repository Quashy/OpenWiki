from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.services.retrieval.dense import RetrievalResult


def sparse_score(search_text: str, query: str) -> float:
    normalized_text = search_text.lower()
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return 0.0
    return sum(normalized_text.count(term) for term in terms) / len(terms)


async def sparse_search(
    session: AsyncSession,
    *,
    kb_ids: list[str],
    query: str,
    top_k: int = 8,
) -> list[RetrievalResult]:
    if session.bind and session.bind.dialect.name == "postgresql":
        result = await session.execute(
            text(
                """
                SELECT id, content, header_path, document_id, chunk_type,
                       bigm_similarity(search_text, :query) AS score
                FROM chunks
                WHERE kb_id = ANY(:kb_ids)
                  AND search_text &@~ :query
                ORDER BY score DESC
                LIMIT :top_k
                """
            ),
            {"query": query, "kb_ids": kb_ids, "top_k": top_k},
        )
        return [
            RetrievalResult(
                chunk_id=row.id,
                content=row.content,
                header_path=list(row.header_path or []),
                document_id=row.document_id,
                chunk_type=row.chunk_type,
                score=float(row.score or 0),
            )
            for row in result
        ]

    result = await session.execute(select(Chunk).where(Chunk.kb_id.in_(kb_ids)))
    scored = [
        RetrievalResult(
            chunk_id=chunk.id,
            content=chunk.content,
            header_path=chunk.header_path,
            document_id=chunk.document_id,
            chunk_type=chunk.chunk_type,
            score=sparse_score(chunk.search_text, query),
        )
        for chunk in result.scalars()
    ]
    return [item for item in sorted(scored, key=lambda item: item.score, reverse=True) if item.score > 0][:top_k]
