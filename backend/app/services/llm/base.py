from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

