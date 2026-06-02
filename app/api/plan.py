from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.services import plan_service
from app.schemas.plan import Plan, PlanAndSessionListResponse, PlanResponse
from app.schemas.response import success_response
from app.schemas.plan import PlanRequest


router = APIRouter()

@router.get("/plan", response_model=PlanAndSessionListResponse)
async def get_plan_and_session_list(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanAndSessionListResponse:
    plan_list = await plan_service.get_plan(db, user_id=current_user.id)
    return success_response(data=plan_list, response_model=PlanAndSessionListResponse)


@router.put("/plan", response_model=PlanResponse)
async def create_plan(
    plan_request: PlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    new_plan = await plan_service.create_plan(db, plan_request.name, user_id=current_user.id)
    return success_response(data=new_plan, response_model=PlanResponse)

@router.delete("/plan/{plan_id}")
async def delete_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await plan_service.delete_plan_by_id(db, plan_id, user_id=current_user.id)
    return success_response()

@router.post("/plan")
async def update_plan(
    plan: Plan,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await plan_service.update_plan_by_id(db, plan, user_id=current_user.id)
    return success_response()
