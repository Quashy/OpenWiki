from dataclasses import replace

from app.services.retrieval.dense import RetrievalResult


def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)


def reciprocal_rank_fusion(
    result_sets: list[list[RetrievalResult]],
    *,
    k: int = 60,
    wiki_boost: float = 1.2,
    top_k: int = 8,
) -> list[RetrievalResult]:
    best_by_chunk: dict[str, RetrievalResult] = {}
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    order = 0

    for results in result_sets:
        for rank, item in enumerate(results):
            if item.chunk_id not in first_seen:
                first_seen[item.chunk_id] = order
                order += 1
            best = best_by_chunk.get(item.chunk_id)
            if best is None or item.score > best.score:
                best_by_chunk[item.chunk_id] = item
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + rrf_score(rank, k)

    fused: list[RetrievalResult] = []
    for chunk_id, item in best_by_chunk.items():
        score = scores[chunk_id] * (wiki_boost if item.chunk_type == "wiki_page" else 1.0)
        fused.append(replace(item, score=score))

    return sorted(
        fused,
        key=lambda item: (-item.score, first_seen[item.chunk_id], item.chunk_id),
    )[:top_k]
