from app.schemas import Citation


GENERAL_CHAT_SYSTEM_PROMPT = (
    "你是 OpenWiki V2 的企业知识库助手。"
    "当没有提供知识库上下文时，正常回答通用问题、寒暄、能力说明和使用帮助。"
    "不要声称回答来自知识库，不要编造文档、Wiki 页面或引用编号。"
    "如果用户询问特定知识库事实，而当前没有上下文可用，说明这部分需要知识库证据才能确认。"
)

RAG_SYSTEM_PROMPT = (
    "你是 OpenWiki V2 的企业知识库助手。"
    "优先使用给定上下文回答知识库相关问题。"
    "凡使用上下文事实，必须使用 [1]、[2] 这样的编号引用，编号只能来自上下文。"
    "如果上下文不足以支持某个事实，明确说明无法从当前知识库确认，不要编造。"
    "对于寒暄、身份介绍或使用帮助，可以自然回答，但不要附加知识库引用。"
)


def build_general_chat_messages(
    *,
    question: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": GENERAL_CHAT_SYSTEM_PROMPT,
        },
        *history[-20:],
        {
            "role": "user",
            "content": question,
        },
    ]


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
            "content": RAG_SYSTEM_PROMPT,
        },
        *history_messages,
        {
            "role": "user",
            "content": f"上下文：\n{context}\n\n问题：{question}",
        },
    ]
