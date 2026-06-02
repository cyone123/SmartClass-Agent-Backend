from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies.db import get_db
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, RegisterRequest, RegisterResponse, UserPublic
from app.schemas.response import success_response
from app.services import auth_service

router = APIRouter()


@router.post("/auth/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    user = await auth_service.register_user(
        db,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
    )
    return success_response(data=user, response_model=RegisterResponse)


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    data = await auth_service.build_login_payload(
        db,
        username=payload.username,
        password=payload.password,
    )
    return success_response(data=data, response_model=LoginResponse)


@router.get("/auth/me", response_model=MeResponse)
async def me(current_user=Depends(get_current_user)) -> MeResponse:
    return success_response(data=current_user, response_model=MeResponse)
