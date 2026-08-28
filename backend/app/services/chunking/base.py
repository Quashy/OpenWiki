from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    seq: int
    content: str
    header_path: list[str]
    start_pos: int
    end_pos: int


class Chunker(ABC):
    def __init__(self, *, chunk_size: int = 512, chunk_overlap: int = 80) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def split(self, content: str) -> list[Chunk]:
        raise NotImplementedError
