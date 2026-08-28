from app.services.chunking.markdown_chunker import MarkdownChunker
from app.services.chunking.text_chunker import TextChunker


def test_markdown_chunker_keeps_h1_h2_h3_header_path() -> None:
    content = "# 产品\n\n总览\n\n## 计费方式\n\n### 关键词快车\n\nCPC 最低出价 0.3 元。"

    chunks = MarkdownChunker(chunk_size=512, chunk_overlap=80).split(content)

    assert [chunk.header_path for chunk in chunks] == [
        ["产品"],
        ["产品", "计费方式"],
        ["产品", "计费方式", "关键词快车"],
    ]
    assert chunks[0].seq == 1
    assert content[chunks[-1].start_pos : chunks[-1].end_pos] == chunks[-1].content


def test_markdown_chunker_does_not_overlap_header_boundaries() -> None:
    content = "# A\n\n" + ("甲" * 40) + "\n\n# B\n\n" + ("乙" * 40)

    chunks = MarkdownChunker(chunk_size=32, chunk_overlap=8).split(content)
    a_chunks = [chunk for chunk in chunks if chunk.header_path == ["A"]]
    b_chunks = [chunk for chunk in chunks if chunk.header_path == ["B"]]

    assert a_chunks
    assert b_chunks
    assert max(chunk.end_pos for chunk in a_chunks) <= min(chunk.start_pos for chunk in b_chunks)


def test_markdown_chunker_splits_long_section_with_overlap() -> None:
    content = "# 长章节\n\n" + "。".join([f"句子{i}" for i in range(40)])

    chunks = MarkdownChunker(chunk_size=64, chunk_overlap=10).split(content)

    assert len(chunks) > 1
    assert all(chunk.header_path == ["长章节"] for chunk in chunks)
    assert chunks[1].start_pos < chunks[0].end_pos


def test_text_chunker_uses_empty_header_path() -> None:
    content = "第一段。" * 40

    chunks = TextChunker(chunk_size=50, chunk_overlap=8).split(content)

    assert len(chunks) > 1
    assert all(chunk.header_path == [] for chunk in chunks)
    assert chunks[0].seq == 1
