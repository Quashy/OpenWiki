from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.admin import get_ollama_client
from app.deps import CurrentPrincipalDep, Principal, SessionDep, SettingsDep, require_roles
from app.schemas import (
    KnowledgeBaseOut,
    KnowledgeBasePage,
    KnowledgeBaseUpdateRequest,
    SourceKnowledgeBaseCreateRequest,
    WikiKnowledgeBaseCreateRequest,
    WikiSourceBindingOut,
    WikiSourceBindingRequest,
)
from app.services.kb_service import (
    bind_source,
    create_kb,
    delete_kb,
    get_kb,
    kb_out,
    list_kbs,
    unbind_source,
    update_kb,
)
from app.services.model_service import OllamaClient

router = APIRouter(prefix="/kbs", tags=["knowledge-bases"])

AdminPrincipal = Annotated[Principal, Depends(require_roles("admin"))]


@router.get("", response_model=KnowledgeBasePage)
async def list_knowledge_bases(
    principal: CurrentPrincipalDep,
    session: SessionDep,
    kb_type: str | None = Query(default=None, alias="type"),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> KnowledgeBasePage:
    return await list_kbs(
        session,
        workspace_id=principal.workspace.id,
        kb_type=kb_type,
        status=status_filter,
        q=q,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: SourceKnowledgeBaseCreateRequest | WikiKnowledgeBaseCreateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> KnowledgeBaseOut:
    return await create_kb(
        session,
        settings=settings,
        client=client,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        payload=payload.model_dump(),
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(
    kb_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> KnowledgeBaseOut:
    kb = await get_kb(session, workspace_id=principal.workspace.id, kb_id=kb_id)
    return await kb_out(session, kb)


@router.patch("/{kb_id}", response_model=KnowledgeBaseOut)
async def patch_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseUpdateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
) -> KnowledgeBaseOut:
    return await update_kb(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        payload=payload.model_dump(exclude_unset=True),
    )


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: str,
    principal: AdminPrincipal,
    session: SessionDep,
) -> Response:
    await delete_kb(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kb_id}/bindings", response_model=WikiSourceBindingOut, status_code=201)
async def bind_source_knowledge_base(
    kb_id: str,
    payload: WikiSourceBindingRequest,
    principal: AdminPrincipal,
    session: SessionDep,
) -> WikiSourceBindingOut:
    return await bind_source(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        wiki_kb_id=kb_id,
        source_kb_id=payload.source_kb_id,
    )


@router.delete("/{kb_id}/bindings/{source_kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_source_knowledge_base(
    kb_id: str,
    source_kb_id: str,
    principal: AdminPrincipal,
    session: SessionDep,
) -> Response:
    await unbind_source(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        wiki_kb_id=kb_id,
        source_kb_id=source_kb_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
