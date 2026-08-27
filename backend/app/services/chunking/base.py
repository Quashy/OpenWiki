from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    content: str
    header_path: list[str]
    start_pos: int
    end_pos: int


class Chunker(ABC):
    @abstractmethod
    def split(self, content: str) -> list[Chunk]:
        raise NotImplementedError

