from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import ApiError
from app.models import User, Workspace, WorkspaceMember
from app.schemas import WorkspaceMemberOut, WorkspaceOut
from app.services.audit_service import record_audit
from app.services.auth_service import member_out


async def update_workspace_name(
    session: AsyncSession,
    *,
    workspace: Workspace,
    actor_id: str,
    name: str,
) -> WorkspaceOut:
    workspace.name = name
    await record_audit(
        session,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="workspace.update",
        resource_type="workspace",
        resource_id=workspace.id,
        details={"name": name},
    )
    await session.commit()
    return WorkspaceOut.model_validate(workspace)


async def list_members(session: AsyncSession, workspace_id: str) -> list[WorkspaceMemberOut]:
    result = await session.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .options(selectinload(WorkspaceMember.user))
        .order_by(WorkspaceMember.created_at)
    )
    return [member_out(member) for member in result.scalars()]


async def add_member(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    username: str,
    role: str,
) -> WorkspaceMemberOut:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None:
        raise ApiError("validation_error", "用户不存在", 422)

    existing = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if existing is not None:
        raise ApiError("conflict", "用户已是团队成员", 409)

    member = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=role)
    session.add(member)
    await session.flush()
    member.user = user
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="member.add",
        resource_type="member",
        resource_id=user.id,
        details={"username": username, "role": role},
    )
    await session.commit()
    return member_out(member)


async def admin_count(session: AsyncSession, workspace_id: str) -> int:
    count = await session.scalar(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "admin",
        )
    )
    return int(count or 0)


async def update_member_role(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    user_id: str,
    role: str,
) -> WorkspaceMemberOut:
    member = await session.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .options(selectinload(WorkspaceMember.user))
    )
    if member is None:
        raise ApiError("not_found", "成员不存在", 404)
    if member.role == "admin" and role != "admin" and await admin_count(session, workspace_id) <= 1:
        raise ApiError("last_admin_required", "不能降级最后一名管理员", 409)

    member.role = role
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="member.update_role",
        resource_type="member",
        resource_id=user_id,
        details={"role": role},
    )
    await session.commit()
    return member_out(member)


async def remove_member(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    user_id: str,
) -> None:
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise ApiError("not_found", "成员不存在", 404)
    if member.role == "admin" and await admin_count(session, workspace_id) <= 1:
        raise ApiError("last_admin_required", "不能移除最后一名管理员", 409)

    await session.delete(member)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="member.remove",
        resource_type="member",
        resource_id=user_id,
    )
    await session.commit()
