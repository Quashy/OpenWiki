from app.services.chunking.base import Chunk, Chunker


class TextChunker(Chunker):
    def split(self, content: str) -> list[Chunk]:
        return [Chunk(content=content, header_path=[], start_pos=0, end_pos=len(content))]

