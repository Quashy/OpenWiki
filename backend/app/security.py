import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.config import Settings
from app.errors import ApiError

TokenKind = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class DecodedToken:
    user_id: str
    kind: TokenKind


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str, settings: Settings) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = datetime.now(UTC) + expires_delta
    payload: dict[str, Any] = {"sub": user_id, "kind": "access", "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(
        expires_delta.total_seconds()
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def refresh_expires_at(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)


def decode_token(token: str, settings: Settings, expected_kind: TokenKind) -> DecodedToken:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ApiError("unauthorized", "认证凭据无效", 401) from exc

    user_id = payload.get("sub")
    kind = payload.get("kind")
    if not isinstance(user_id, str) or kind != expected_kind:
        raise ApiError("unauthorized", "认证凭据无效", 401)
    return DecodedToken(user_id=user_id, kind=expected_kind)


def encryption_key(settings: Settings) -> bytes:
    raw = settings.encryption_key
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) in {16, 24, 32}:
            return decoded
    except ValueError:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(value: str, settings: Settings) -> str:
    aes = AESGCM(encryption_key(settings))
    nonce = secrets.token_bytes(12)
    encrypted = aes.encrypt(nonce, value.encode("utf-8"), None)
    return base64.b64encode(nonce + encrypted).decode("ascii")


def decrypt_secret(value: str, settings: Settings) -> str:
    raw = base64.b64decode(value)
    aes = AESGCM(encryption_key(settings))
    return aes.decrypt(raw[:12], raw[12:], None).decode("utf-8")


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return f"{value[:2]}******"
    return f"{value[:4]}******{value[-4:]}"
