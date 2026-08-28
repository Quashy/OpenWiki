from app.services.embedding.base import EmbeddingProvider
from app.services.model_service import OllamaClient


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, client: OllamaClient, base_url: str, tag: str) -> None:
        self.client = client
        self.base_url = base_url
        self.tag = tag

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [await self.client.embed(self.base_url, self.tag, text) for text in texts]
