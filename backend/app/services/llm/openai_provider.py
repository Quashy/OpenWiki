from app.services.llm.base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

