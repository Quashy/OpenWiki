import re
from dataclasses import dataclass

from app.services.chunking.base import Chunk, Chunker

HEADER_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class Section:
    start: int
    end: int
    header_path: list[str]


class MarkdownChunker(Chunker):
    def split(self, content: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in self._sections(content):
            for start, end in split_range(content, section.start, section.end, self.chunk_size, self.chunk_overlap):
                if start >= end:
                    continue
                chunks.append(
                    Chunk(
                        seq=len(chunks) + 1,
                        content=content[start:end],
                        header_path=section.header_path,
                        start_pos=start,
                        end_pos=end,
                    )
                )
        return chunks

    def _sections(self, content: str) -> list[Section]:
        headings: list[tuple[int, int, int, str, list[str]]] = []
        h1: str | None = None
        h2: str | None = None

        offset = 0
        for line in content.splitlines(keepends=True):
            match = HEADER_RE.match(line.rstrip("\r\n"))
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                if level == 1:
                    h1 = title
                    h2 = None
                    path = [title]
                elif level == 2:
                    h2 = title
                    path = [item for item in [h1, title] if item]
                else:
                    path = [item for item in [h1, h2, title] if item]
                headings.append((offset, offset + len(line), level, title, path))
            offset += len(line)

        if not headings:
            start, end = trim_range(content, 0, len(content))
            return [Section(start=start, end=end, header_path=[])] if start < end else []

        sections: list[Section] = []
        if headings[0][0] > 0:
            start, end = trim_range(content, 0, headings[0][0])
            if start < end:
                sections.append(Section(start=start, end=end, header_path=[]))

        for index, heading in enumerate(headings):
            start = heading[0]
            end = headings[index + 1][0] if index + 1 < len(headings) else len(content)
            start, end = trim_range(content, start, end)
            if start < end:
                sections.append(Section(start=start, end=end, header_path=heading[4]))
        return sections


def trim_range(content: str, start: int, end: int) -> tuple[int, int]:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end


def split_range(
    content: str,
    start: int,
    end: int,
    chunk_size: int,
    chunk_overlap: int,
) -> list[tuple[int, int]]:
    start, end = trim_range(content, start, end)
    if end - start <= chunk_size:
        return [(start, end)] if start < end else []

    ranges: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        target = min(cursor + chunk_size, end)
        cut = target if target == end else choose_cut(content, cursor, target)
        if cut <= cursor:
            cut = target
        chunk_start, chunk_end = trim_range(content, cursor, cut)
        if chunk_start < chunk_end:
            ranges.append((chunk_start, chunk_end))
        if cut >= end:
            break
        next_cursor = max(cursor + 1, cut - chunk_overlap)
        cursor, _ = trim_range(content, next_cursor, end)
    return ranges


def choose_cut(content: str, start: int, target: int) -> int:
    window = content[start:target]
    minimum = max(1, len(window) // 2)
    paragraph = window.rfind("\n\n")
    if paragraph >= minimum:
        return start + paragraph + 2

    for index in range(len(window) - 1, minimum - 1, -1):
        if window[index] in "。！？；\n.!?;":
            return start + index + 1
    return target
