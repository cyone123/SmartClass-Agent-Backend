from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_env
from app.dependencies.db import get_db
from app.models.user import User

ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24
DEFAULT_PASSWORD_ITERATIONS = 210_000
bearer_scheme = HTTPBearer(auto_error=False)


def get_jwt_secret_key() -> str:
    return get_env("JWT_SECRET_KEY", "smartclass-dev-secret") or "smartclass-dev-secret"


def get_token_expire_seconds() -> int:
    raw = get_env("JWT_ACCESS_TOKEN_EXPIRE_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_TOKEN_EXPIRE_SECONDS
    return int(raw)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = DEFAULT_PASSWORD_ITERATIONS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    encoded = base64.urlsafe_b64encode(salt).decode("ascii")
    return f"pbkdf2_sha256${iterations}${encoded}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_hex = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
    return hmac.compare_digest(candidate, digest_hex)


def create_access_token(*, user: User, expires_delta: timedelta | None = None) -> tuple[str, int]:
    expires_delta = expires_delta or timedelta(seconds=get_token_expire_seconds())
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": expire_at,
    }
    token = jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


async def get_current_user_from_token(db: AsyncSession, token: str) -> User:
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc
    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


async def get_current_user_from_auth_or_query(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials is not None else access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return await get_current_user_from_token(db, token)
