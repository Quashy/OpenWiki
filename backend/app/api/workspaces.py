from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.deps import CurrentPrincipalDep, Principal, SessionDep, require_roles
from app.schemas import (
    MemberCreateRequest,
    MemberListResponse,
    MemberRoleUpdateRequest,
    WorkspaceMemberOut,
    WorkspaceOut,
    WorkspaceUpdateRequest,
)
from app.services.workspace_service import (
    add_member,
    list_members,
    remove_member,
    update_member_role,
    update_workspace_name,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

AdminPrincipal = Annotated[Principal, Depends(require_roles("admin"))]


@router.get("/current", response_model=WorkspaceOut)
async def get_current_workspace(principal: CurrentPrincipalDep) -> WorkspaceOut:
    return WorkspaceOut.model_validate(principal.workspace)


@router.patch("/current", response_model=WorkspaceOut)
async def update_current_workspace(
    payload: WorkspaceUpdateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
) -> WorkspaceOut:
    return await update_workspace_name(
        session,
        workspace=principal.workspace,
        actor_id=principal.user.id,
        name=payload.name,
    )


@router.get("/current/members", response_model=MemberListResponse)
async def get_members(principal: AdminPrincipal, session: SessionDep) -> MemberListResponse:
    return MemberListResponse(items=await list_members(session, principal.workspace.id))


@router.post(
    "/current/members",
    response_model=WorkspaceMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_member(
    payload: MemberCreateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
) -> WorkspaceMemberOut:
    return await add_member(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        username=payload.username,
        role=payload.role,
    )


@router.patch("/current/members/{user_id}", response_model=WorkspaceMemberOut)
async def patch_member_role(
    user_id: str,
    payload: MemberRoleUpdateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
) -> WorkspaceMemberOut:
    return await update_member_role(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        user_id=user_id,
        role=payload.role,
    )


@router.delete("/current/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    user_id: str,
    principal: AdminPrincipal,
    session: SessionDep,
) -> Response:
    await remove_member(
        session,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        user_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
