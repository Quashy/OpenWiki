from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.database import get_session
from app.errors import ApiError
from app.models import User, Workspace, WorkspaceMember
from app.security import decode_token

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    workspace: Workspace
    membership: WorkspaceMember


def get_request_id(request: Request) -> str:
    return cast(str, request.state.request_id)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise ApiError("unauthorized", "未登录", 401)
    decoded = decode_token(credentials.credentials, settings, "access")
    user = await session.get(User, decoded.user_id)
    if user is None:
        raise ApiError("unauthorized", "用户不存在", 401)
    return user


async def get_current_principal(
    user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
) -> Principal:
    result = await session.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .options(selectinload(WorkspaceMember.workspace), selectinload(WorkspaceMember.user))
    )
    membership = result.scalars().first()
    if membership is None:
        raise ApiError("forbidden", "当前用户尚未加入团队", 403)
    return Principal(user=user, workspace=membership.workspace, membership=membership)


CurrentPrincipalDep = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*roles: str):
    async def dependency(principal: CurrentPrincipalDep) -> Principal:
        if principal.membership.role not in roles:
            raise ApiError("forbidden", "没有权限执行该操作", 403)
        return principal

    return dependency
