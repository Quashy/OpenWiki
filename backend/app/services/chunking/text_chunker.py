from app.services.chunking.base import Chunk, Chunker
from app.services.chunking.markdown_chunker import split_range


class TextChunker(Chunker):
    def split(self, content: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for start, end in split_range(content, 0, len(content), self.chunk_size, self.chunk_overlap):
            chunks.append(
                Chunk(
                    seq=len(chunks) + 1,
                    content=content[start:end],
                    header_path=[],
                    start_pos=start,
                    end_pos=end,
                )
            )
        return chunks
