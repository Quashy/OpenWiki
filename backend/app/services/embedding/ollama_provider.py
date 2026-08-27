from app.services.embedding.base import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

