import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import ChatMessage, ChatSession, Chunk, Document, KnowledgeBase, WikiPage
from app.models.m1 import now_utc
from app.prompts.fallback import deterministic_answer, no_evidence_answer
from app.prompts.qa import build_qa_messages
from app.prompts.rewrite import rewrite_query
from app.schemas import (
    ChatMessageOut,
    ChatMessagePage,
    ChatSessionOut,
    ChatSessionPage,
    Citation,
)
from app.services.audit_service import record_audit
from app.services.llm.base import LLMProvider
from app.services.model_service import OllamaClient
from app.services.observability import Observability
from app.services.retrieval.dense import RetrievalResult
from app.services.retrieval.retriever import HybridSearchResult, hybrid_search
from app.services.wiki.pipeline import ObservedLLMProvider, build_llm_provider

logger = structlog.get_logger(__name__)


def default_title(title: str | None) -> str:
    clean = (title or "").strip()
    return clean[:256] if clean else "新会话"


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def require_chat_session(
    session: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
) -> ChatSession:
    chat_session = await session.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
        )
    )
    if chat_session is None:
        raise ApiError("not_found", "会话不存在", 404)
    return chat_session


async def require_queryable_kb(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
) -> KnowledgeBase:
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if kb is None:
        raise ApiError("not_found", "知识库不存在", 404)
    if kb.status != "active":
        raise ApiError("kb_unavailable", "KB 不可检索", 409)
    return kb


async def create_chat_session(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    title: str | None,
) -> ChatSessionOut:
    await require_queryable_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    chat_session = ChatSession(
        workspace_id=workspace_id,
        user_id=actor_id,
        kb_id=kb_id,
        title=default_title(title),
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(chat_session)
    await session.flush()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="chat.session_create",
        resource_type="chat_session",
        resource_id=chat_session.id,
        details={"kb_id": kb_id},
    )
    await session.commit()
    return ChatSessionOut.model_validate(chat_session)


async def list_chat_sessions(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str | None,
    page: int,
    page_size: int,
) -> ChatSessionPage:
    conditions: list[Any] = [ChatSession.workspace_id == workspace_id]
    if kb_id:
        conditions.append(ChatSession.kb_id == kb_id)
    total = await session.scalar(select(func.count()).select_from(ChatSession).where(*conditions))
    result = await session.execute(
        select(ChatSession)
        .where(*conditions)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ChatSessionPage(
        items=[ChatSessionOut.model_validate(item) for item in result.scalars()],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


async def update_chat_session(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    session_id: str,
    title: str,
) -> ChatSessionOut:
    chat_session = await require_chat_session(session, workspace_id=workspace_id, session_id=session_id)
    chat_session.title = title.strip()
    chat_session.updated_at = now_utc()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="chat.session_update",
        resource_type="chat_session",
        resource_id=chat_session.id,
        details={"title": chat_session.title},
    )
    await session.commit()
    return ChatSessionOut.model_validate(chat_session)


async def delete_chat_session(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    session_id: str,
) -> None:
    chat_session = await require_chat_session(session, workspace_id=workspace_id, session_id=session_id)
    await session.delete(chat_session)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="chat.session_delete",
        resource_type="chat_session",
        resource_id=session_id,
        details={"kb_id": chat_session.kb_id},
    )
    await session.commit()


async def list_chat_messages(
    session: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    page: int,
    page_size: int,
) -> ChatMessagePage:
    chat_session = await require_chat_session(session, workspace_id=workspace_id, session_id=session_id)
    total = await session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == chat_session.id)
    )
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ChatMessagePage(
        items=[ChatMessageOut.model_validate(item) for item in result.scalars()],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


async def recent_history(
    session: AsyncSession,
    *,
    chat_session_id: str,
    turns: int,
) -> list[dict[str, str]]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(turns * 2)
    )
    messages = list(reversed(list(result.scalars())))
    return [{"role": item.role, "content": item.content} for item in messages]


async def citation_rows(
    session: AsyncSession,
    results: list[RetrievalResult],
) -> list[Citation]:
    document_ids = [item.document_id for item in results if item.document_id]
    page_ids = [item.source_page_id for item in results if item.source_page_id]
    documents = {}
    pages = {}
    if document_ids:
        documents = {
            item.id: item
            for item in (
                await session.execute(select(Document).where(Document.id.in_(document_ids)))
            ).scalars()
        }
    if page_ids:
        pages = {
            item.id: item
            for item in (
                await session.execute(select(WikiPage).where(WikiPage.id.in_(page_ids)))
            ).scalars()
        }

    citations: list[Citation] = []
    for index, item in enumerate(results, start=1):
        document = documents.get(item.document_id or "")
        page = pages.get(item.source_page_id or "")
        citations.append(
            Citation(
                id=index,
                source_type="wiki_page" if item.chunk_type == "wiki_page" else "document",
                kb_id=item.kb_id,
                document_id=item.document_id,
                wiki_page_id=item.source_page_id,
                chunk_id=item.chunk_id,
                filename=document.filename if document else None,
                title=page.title if page else None,
                header_path=item.header_path,
                snippet=item.content[:500],
            )
        )
    return citations


def retrieval_metadata(result: HybridSearchResult) -> dict[str, int]:
    return {
        "dense_count": len(result.dense),
        "sparse_count": len(result.sparse),
        "graph_count": len(result.graph),
        "fused_count": len(result.fused),
    }


async def stream_chat_answer(
    session: AsyncSession,
    *,
    settings: Settings,
    ollama_client: OllamaClient,
    workspace_id: str,
    actor_id: str,
    session_id: str,
    question: str,
    llm_provider: LLMProvider | None = None,
) -> AsyncIterator[str]:
    chat_session = await require_chat_session(session, workspace_id=workspace_id, session_id=session_id)
    kb = await require_queryable_kb(session, workspace_id=workspace_id, kb_id=chat_session.kb_id)
    kb_id = chat_session.kb_id
    observability = Observability(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
    trace = observability.trace(
        name="chat_qa",
        metadata={
                "workspace_id": workspace_id,
                "kb_id": kb_id,
            "user_id": actor_id,
            "session_id": session_id,
        },
    )
    llm = llm_provider if llm_provider is not None else await build_llm_provider(session, settings=settings)
    if llm is not None:
        llm = ObservedLLMProvider(llm, trace)

    user_message = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=question,
        citations=[],
        token_usage={},
        created_at=now_utc(),
    )
    session.add(user_message)
    chat_session.updated_at = now_utc()
    await session.commit()

    answer = ""
    citations: list[Citation] = []
    assistant_message: ChatMessage | None = None
    trace_level = "DEFAULT"
    trace_status_message = "completed"

    try:
        yield sse_event("progress", {"stage": "history", "message": "正在加载会话历史..."})
        history = await recent_history(session, chat_session_id=chat_session.id, turns=settings.chat_history_turns)
        with trace.span(name="query_understand", metadata={"history_count": len(history)}):
            rewritten_query = await rewrite_query(llm, question, history[:-1])

        yield sse_event("progress", {"stage": "search", "message": "正在检索知识库..."})
        with trace.span(name="search", metadata={"query": rewritten_query}):
            search_result = await hybrid_search(
                session,
                settings=settings,
                ollama_client=ollama_client,
                kb=kb,
                query=rewritten_query,
                top_k=settings.retrieval_top_k,
            )
        with trace.span(name="search.dense", metadata={"result_count": len(search_result.dense)}):
            pass
        with trace.span(name="search.sparse", metadata={"result_count": len(search_result.sparse)}):
            pass
        with trace.span(name="search.graph", metadata={"result_count": len(search_result.graph)}):
            pass
        trace.update(metadata={**retrieval_metadata(search_result), "rewritten_query": rewritten_query})

        with trace.span(name="merge_filter", metadata=retrieval_metadata(search_result)):
            citations = await citation_rows(session, search_result.fused)

        yield sse_event("progress", {"stage": "completion", "message": "正在生成回答..."})
        if not citations:
            answer = no_evidence_answer()
            yield sse_event("token", {"content": answer})
        elif llm is None:
            answer = deterministic_answer(question, citations)
            yield sse_event("token", {"content": answer})
        else:
            messages = build_qa_messages(question=question, history=history[:-1], citations=citations)
            async for token in llm.stream(
                messages,
                temperature=0.2,
                prompt_metadata={"prompt_stage": "completion"},
            ):
                answer += token
                yield sse_event("token", {"content": token})

        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=answer,
            citations=[item.model_dump() for item in citations],
            trace_id=trace.id,
            token_usage={"output_chars": len(answer)},
            created_at=now_utc(),
        )
        session.add(assistant_message)
        chat_session.updated_at = now_utc()
        if chat_session.title == "新会话":
            chat_session.title = question.strip()[:40] or "新会话"
        await session.commit()
        yield sse_event(
            "done",
            {
                "message_id": assistant_message.id,
                "citations": [item.model_dump() for item in citations],
                "trace_id": trace.id,
            },
        )
    except Exception as exc:
        trace_level = "ERROR"
        trace_status_message = str(exc)
        await session.rollback()
        if isinstance(exc, ApiError):
            code = exc.code
            message = exc.message
        else:
            logger.exception(
                "chat_stream_failed",
                workspace_id=workspace_id,
                kb_id=kb_id,
                session_id=session_id,
                user_id=actor_id,
            )
            code = "chat_failed"
            message = "问答失败，请稍后重试"
        yield sse_event("error", {"code": code, "message": message})
    finally:
        trace.finish(level=trace_level, status_message=trace_status_message)
