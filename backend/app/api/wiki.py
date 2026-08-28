from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status

from app.deps import CurrentPrincipalDep, Principal, SessionDep, require_roles
from app.schemas import (
    TaskAcceptedResponse,
    WikiGraph,
    WikiIngestRequest,
    WikiPageListResponse,
    WikiPageOut,
    WikiRebuildRequest,
)
from app.services.wiki.page_service import get_wiki_graph, get_wiki_page, list_wiki_pages
from app.services.wiki.pipeline import create_wiki_task

router = APIRouter(tags=["wiki"])

EditorPrincipal = Annotated[Principal, Depends(require_roles("admin", "editor"))]


@router.post(
    "/wiki/{kb_id}/ingest",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_wiki(
    kb_id: str,
    principal: EditorPrincipal,
    session: SessionDep,
    payload: WikiIngestRequest | None = Body(default=None),
) -> TaskAcceptedResponse:
    return await create_wiki_task(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        task_type="wiki_ingest",
        document_ids=payload.document_ids if payload else None,
    )


@router.post(
    "/wiki/{kb_id}/rebuild",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_wiki(
    kb_id: str,
    _: WikiRebuildRequest,
    principal: EditorPrincipal,
    session: SessionDep,
) -> TaskAcceptedResponse:
    return await create_wiki_task(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        task_type="wiki_rebuild",
    )


@router.get("/wiki/{kb_id}/pages", response_model=WikiPageListResponse)
async def get_wiki_pages(
    kb_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=128),
    page_type: str | None = None,
) -> WikiPageListResponse:
    return await list_wiki_pages(
        session,
        workspace_id=principal.workspace.id,
        kb_id=kb_id,
        q=q,
        page_type=page_type,
    )


@router.get("/wiki/{kb_id}/graph", response_model=WikiGraph)
async def get_graph(
    kb_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
    entity_type: str | None = None,
    relation_type: str | None = None,
) -> WikiGraph:
    return await get_wiki_graph(
        session,
        workspace_id=principal.workspace.id,
        kb_id=kb_id,
        entity_type=entity_type,
        relation_type=relation_type,
    )


@router.get("/wiki-pages/{page_id}", response_model=WikiPageOut)
async def get_page(
    page_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> WikiPageOut:
    return await get_wiki_page(session, workspace_id=principal.workspace.id, page_id=page_id)
