from fastapi import APIRouter, Response, status

from app.deps import SessionDep, SettingsDep
from app.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPair,
)
from app.services.auth_service import login_user, logout_user, refresh_tokens, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> AuthResponse:
    return await register_user(
        session,
        username=payload.username,
        password=payload.password,
        settings=settings,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> AuthResponse:
    return await login_user(
        session,
        username=payload.username,
        password=payload.password,
        settings=settings,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshTokenRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    return await refresh_tokens(session, refresh_token=payload.refresh_token, settings=settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: SessionDep,
    payload: RefreshTokenRequest | None = None,
) -> Response:
    await logout_user(session, refresh_token=payload.refresh_token if payload else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
