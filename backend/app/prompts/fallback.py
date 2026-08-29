from app.schemas import Citation


def no_evidence_answer() -> str:
    return "当前知识库没有足够证据回答这个问题。"


def deterministic_answer(question: str, citations: list[Citation]) -> str:
    if not citations:
        return no_evidence_answer()
    lead = citations[0]
    return f"根据当前知识库，{lead.snippet} [{lead.id}]"
