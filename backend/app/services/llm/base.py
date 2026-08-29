from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


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

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        yield await self.complete(
            messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            prompt_metadata=prompt_metadata,
        )
