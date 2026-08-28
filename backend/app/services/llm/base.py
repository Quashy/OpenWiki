from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        raise NotImplementedError
