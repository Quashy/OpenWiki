from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.deps import CurrentPrincipalDep, Principal, SessionDep, SettingsDep, require_roles
from app.schemas import (
    DocumentDetail,
    DocumentPage,
    DocumentUploadResponse,
    TagCreateRequest,
    TagOut,
    TaskAcceptedResponse,
)
from app.services.document_service import (
    create_tag,
    delete_document,
    delete_tag,
    get_document_detail,
    list_documents,
    list_tags,
    retry_document,
    update_tag,
    upload_documents,
)

router = APIRouter(tags=["documents"])

EditorPrincipal = Annotated[Principal, Depends(require_roles("admin", "editor"))]


@router.post(
    "/kbs/{kb_id}/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_kb_documents(
    kb_id: str,
    principal: EditorPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File()],
    tag_ids: Annotated[list[str] | None, Form()] = None,
) -> DocumentUploadResponse:
    return await upload_documents(
        session,
        settings=settings,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        actor_username=principal.user.username,
        kb_id=kb_id,
        files=files,
        tag_ids=tag_ids,
    )


@router.get("/kbs/{kb_id}/documents", response_model=DocumentPage)
async def get_kb_documents(
    kb_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=128),
    tag_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = Query(default="created_at_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocumentPage:
    return await list_documents(
        session,
        workspace_id=principal.workspace.id,
        kb_id=kb_id,
        q=q,
        tag_id=tag_id,
        status=status_filter,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> DocumentDetail:
    return await get_document_detail(
        session,
        workspace_id=principal.workspace.id,
        document_id=document_id,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_document(
    document_id: str,
    principal: EditorPrincipal,
    session: SessionDep,
) -> Response:
    await delete_document(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        document_id=document_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/retry",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_source_document(
    document_id: str,
    principal: EditorPrincipal,
    session: SessionDep,
) -> TaskAcceptedResponse:
    return await retry_document(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        document_id=document_id,
    )


@router.get("/kbs/{kb_id}/tags")
async def get_kb_tags(
    kb_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> dict[str, list[TagOut]]:
    return {"items": await list_tags(session, workspace_id=principal.workspace.id, kb_id=kb_id)}


@router.post("/kbs/{kb_id}/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_kb_tag(
    kb_id: str,
    payload: TagCreateRequest,
    principal: EditorPrincipal,
    session: SessionDep,
) -> TagOut:
    return await create_tag(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        name=payload.name,
    )


@router.patch("/kbs/{kb_id}/tags/{tag_id}", response_model=TagOut)
async def patch_kb_tag(
    kb_id: str,
    tag_id: str,
    payload: TagCreateRequest,
    principal: EditorPrincipal,
    session: SessionDep,
) -> TagOut:
    return await update_tag(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        tag_id=tag_id,
        name=payload.name,
    )


@router.delete("/kbs/{kb_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_tag(
    kb_id: str,
    tag_id: str,
    principal: EditorPrincipal,
    session: SessionDep,
) -> Response:
    await delete_tag(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        kb_id=kb_id,
        tag_id=tag_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
