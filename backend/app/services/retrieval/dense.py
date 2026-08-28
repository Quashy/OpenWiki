import math
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: str
    content: str
    header_path: list[str]
    document_id: str | None
    chunk_type: str
    score: float


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(item)) for item in values) + "]"


def cosine_score(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


async def dense_search(
    session: AsyncSession,
    *,
    kb_ids: list[str],
    query_embedding: list[float],
    top_k: int = 8,
) -> list[RetrievalResult]:
    if session.bind and session.bind.dialect.name == "postgresql":
        result = await session.execute(
            text(
                """
                SELECT id, content, header_path, document_id, chunk_type,
                       1 - (embedding <=> (:query_embedding)::vector) AS score
                FROM chunks
                WHERE kb_id = ANY(:kb_ids)
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> (:query_embedding)::vector
                LIMIT :top_k
                """
            ),
            {
                "query_embedding": vector_literal(query_embedding),
                "kb_ids": kb_ids,
                "top_k": top_k,
            },
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
            score=cosine_score(chunk.embedding or [], query_embedding),
        )
        for chunk in result.scalars()
    ]
    return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]
