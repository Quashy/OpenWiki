from app.services.llm.base import LLMProvider


class DeepSeekLLMProvider(LLMProvider):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

