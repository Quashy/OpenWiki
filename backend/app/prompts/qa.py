from app.schemas import Citation


def build_qa_messages(
    *,
    question: str,
    history: list[dict[str, str]],
    citations: list[Citation],
) -> list[dict[str, str]]:
    context = "\n\n".join(
        (
            f"[{citation.id}] "
            f"{citation.title or citation.filename or '来源'} "
            f"{' > '.join(citation.header_path)}\n"
            f"{citation.snippet}"
        )
        for citation in citations
    )
    history_messages = history[-20:]
    return [
        {
            "role": "system",
            "content": (
                "你是企业内部知识库助手。必须只基于给定上下文回答。"
                "凡使用上下文事实，必须用 [1]、[2] 这样的编号引用。"
                "如果上下文无法支持答案，直接说明当前知识库没有足够证据。"
            ),
        },
        *history_messages,
        {
            "role": "user",
            "content": f"上下文：\n{context}\n\n问题：{question}",
        },
    ]
