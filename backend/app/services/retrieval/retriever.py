from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import KnowledgeBase, ModelSetting
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider
from app.services.model_service import OllamaClient, get_or_create_settings
from app.services.retrieval.dense import RetrievalResult, dense_search
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.graph import graph_search
from app.services.retrieval.sparse import sparse_search


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    dense: list[RetrievalResult]
    sparse: list[RetrievalResult]
    graph: list[RetrievalResult]
    fused: list[RetrievalResult]


async def hybrid_search(
    session: AsyncSession,
    *,
    settings: Settings,
    ollama_client: OllamaClient,
    kb: KnowledgeBase,
    query: str,
    top_k: int | None = None,
) -> HybridSearchResult:
    model_settings: ModelSetting = await get_or_create_settings(session, settings)
    embedding_provider = OllamaEmbeddingProvider(
        client=ollama_client,
        base_url=model_settings.ollama_base_url,
        tag=kb.embedding_model_tag,
    )
    query_embedding = (await embedding_provider.embed([query]))[0]
    per_source_top_k = max(top_k or settings.retrieval_top_k, 20)

    dense_results = await dense_search(
        session,
        kb_ids=[kb.id],
        query_embedding=query_embedding,
        top_k=per_source_top_k,
        min_score=settings.dense_min_score,
    )
    sparse_results = await sparse_search(
        session,
        kb_ids=[kb.id],
        query=query,
        top_k=per_source_top_k,
        min_score=settings.sparse_min_score,
    )
    graph_results = await graph_search(session, kb_id=kb.id, query=query, top_k=per_source_top_k)
    fused = reciprocal_rank_fusion(
        [dense_results, sparse_results, graph_results],
        k=settings.rrf_k,
        top_k=top_k or settings.retrieval_top_k,
    )
    return HybridSearchResult(
        dense=dense_results,
        sparse=sparse_results,
        graph=graph_results,
        fused=fused,
    )
