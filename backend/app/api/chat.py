from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from app.api.admin import get_ollama_client
from app.deps import CurrentPrincipalDep, SessionDep, SettingsDep
from app.schemas import (
    ChatMessagePage,
    ChatSessionCreateRequest,
    ChatSessionOut,
    ChatSessionPage,
    ChatSessionUpdateRequest,
)
from app.services.chat.service import (
    create_chat_session,
    delete_chat_session,
    list_chat_messages,
    list_chat_sessions,
    require_chat_session,
    require_queryable_kb,
    stream_chat_answer,
    update_chat_session,
)
from app.services.model_service import OllamaClient

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreateRequest,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> ChatSessionOut:
    return await create_chat_session(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=payload.kb_id,
        title=payload.title,
    )


@router.get("/sessions", response_model=ChatSessionPage)
async def get_sessions(
    principal: CurrentPrincipalDep,
    session: SessionDep,
    kb_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ChatSessionPage:
    return await list_chat_sessions(
        session,
        workspace_id=principal.workspace.id,
        kb_id=kb_id,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagePage)
async def get_messages(
    session_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ChatMessagePage:
    return await list_chat_messages(
        session,
        workspace_id=principal.workspace.id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}/stream")
async def stream_answer(
    session_id: str,
    question: Annotated[str, Query(min_length=1, max_length=4000)],
    principal: CurrentPrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> StreamingResponse:
    chat_session = await require_chat_session(
        session,
        workspace_id=principal.workspace.id,
        session_id=session_id,
    )
    await require_queryable_kb(session, workspace_id=principal.workspace.id, kb_id=chat_session.kb_id)
    return StreamingResponse(
        stream_chat_answer(
            session,
            settings=settings,
            ollama_client=client,
            workspace_id=principal.workspace.id,
            actor_id=principal.user.id,
            session_id=session_id,
            question=question,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def patch_session(
    session_id: str,
    payload: ChatSessionUpdateRequest,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> ChatSessionOut:
    return await update_chat_session(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        session_id=session_id,
        title=payload.title,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_session(
    session_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> Response:
    await delete_chat_session(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        session_id=session_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
