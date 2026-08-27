from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.errors import ApiError
from app.models import RefreshToken, User, Workspace, WorkspaceMember
from app.schemas import AuthResponse, TokenPair, UserOut, WorkspaceMemberOut, WorkspaceOut
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    refresh_expires_at,
    verify_password,
)
from app.services.audit_service import record_audit


def member_out(member: WorkspaceMember) -> WorkspaceMemberOut:
    return WorkspaceMemberOut(
        id=member.id,
        workspace_id=member.workspace_id,
        user=UserOut.model_validate(member.user),
        role=member.role,
        created_at=member.created_at,
    )


async def issue_tokens(session: AsyncSession, user_id: str, settings: Settings) -> TokenPair:
    access_token, expires_in = create_access_token(user_id, settings)
    refresh_token = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at(settings),
        )
    )
    await session.flush()
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def register_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    settings: Settings,
) -> AuthResponse:
    existing = await session.scalar(select(User).where(User.username == username))
    if existing is not None:
        raise ApiError("conflict", "用户名已存在", 409)

    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    await session.flush()

    workspace: Workspace | None = None
    membership: WorkspaceMember | None = None
    workspace_count = await session.scalar(select(func.count()).select_from(Workspace))
    if workspace_count == 0:
        workspace = Workspace(name="默认团队", created_by=user.id)
        session.add(workspace)
        await session.flush()
        membership = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin")
        session.add(membership)
        await session.flush()
        membership.user = user
        membership.workspace = workspace
        await record_audit(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            action="auth.register_first_admin",
            resource_type="workspace",
            resource_id=workspace.id,
            details={"username": username},
        )

    tokens = await issue_tokens(session, user.id, settings)
    await session.commit()
    return AuthResponse(
        user=UserOut.model_validate(user),
        workspace=WorkspaceOut.model_validate(workspace) if workspace else None,
        membership=member_out(membership) if membership else None,
        tokens=tokens,
    )


async def login_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    settings: Settings,
) -> AuthResponse:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError("unauthorized", "用户名或密码错误", 401)

    membership = await session.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .options(selectinload(WorkspaceMember.workspace), selectinload(WorkspaceMember.user))
    )
    tokens = await issue_tokens(session, user.id, settings)
    await session.commit()
    return AuthResponse(
        user=UserOut.model_validate(user),
        workspace=WorkspaceOut.model_validate(membership.workspace) if membership else None,
        membership=member_out(membership) if membership else None,
        tokens=tokens,
    )


async def refresh_tokens(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings,
) -> TokenPair:
    token_hash = hash_token(refresh_token)
    stored = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    now = datetime.now(UTC)
    expires_at = stored.expires_at if stored else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if stored is None or stored.revoked_at is not None or expires_at <= now:
        raise ApiError("unauthorized", "refresh token 无效", 401)
    stored.revoked_at = now
    tokens = await issue_tokens(session, stored.user_id, settings)
    await session.commit()
    return tokens


async def logout_user(
    session: AsyncSession,
    *,
    refresh_token: str | None,
) -> None:
    if not refresh_token:
        return
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        await session.commit()
