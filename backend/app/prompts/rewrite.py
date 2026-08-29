from app.services.llm.base import LLMProvider


def build_rewrite_messages(question: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    history_text = "\n".join(f"{item['role']}: {item['content']}" for item in history[-20:])
    return [
        {
            "role": "system",
            "content": (
                "你是企业知识库问答的查询理解模块。"
                "将用户问题改写为可独立检索的中文查询，只输出改写后的查询文本。"
            ),
        },
        {
            "role": "user",
            "content": f"历史对话：\n{history_text or '无'}\n\n用户问题：{question}",
        },
    ]


async def rewrite_query(llm: LLMProvider | None, question: str, history: list[dict[str, str]]) -> str:
    if llm is None or not history:
        return question
    text = await llm.complete(
        build_rewrite_messages(question, history),
        temperature=0,
        prompt_metadata={"prompt_stage": "query_understand"},
    )
    return text.strip()[:4000] or question
