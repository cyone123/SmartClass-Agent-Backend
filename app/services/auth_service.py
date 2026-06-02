from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_user_by_username, hash_password, verify_password
from app.models.user import User


async def ensure_default_admin(db: AsyncSession) -> User:
    admin = await get_user_by_username(db, "admin")
    if admin is not None:
        return admin

    admin = User(
        username="admin",
        password_hash=hash_password("admin12345"),
        display_name="系统管理员",
        role="admin",
        is_active=True,
        is_superuser=False,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def register_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
) -> User:
    normalized_username = username.strip()
    if normalized_username.lower() == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot register admin account.")
    existing = await get_user_by_username(db, normalized_username)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists.")
    user = User(
        username=normalized_username,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role="teacher",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, *, username: str, password: str) -> User:
    user = await get_user_by_username(db, username.strip())
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is disabled.")
    return user


async def build_login_payload(db: AsyncSession, *, username: str, password: str) -> dict[str, object]:
    user = await authenticate_user(db, username=username, password=password)
    access_token, expires_in = create_access_token(user=user)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user,
    }


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.id.asc()))
    return list(result.scalars().all())
