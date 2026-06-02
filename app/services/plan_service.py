from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from app.models.plan import Plan
from app.models.session import Session

async def get_plan(db, *, user_id: int):
    query = (
        select(Plan)
        .options(selectinload(Plan.sessions))
        .where(Plan.user_id == user_id)
        .order_by(Plan.id.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def create_plan(db, name, *, user_id: int):
    new_plan = Plan(name=name, user_id=user_id)
    db.add(new_plan)
    await db.commit()
    await db.refresh(new_plan)
    return new_plan

async def ensure_owned_plan(db, plan_id: int, *, user_id: int) -> Plan:
    stmt = select(Plan).where(Plan.id == plan_id, Plan.user_id == user_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found.",
        )
    return plan

async def delete_plan_by_id(db, plan_id, *, user_id: int):
    await ensure_owned_plan(db, plan_id, user_id=user_id)
    stmt = delete(Plan).where(Plan.id == plan_id, Plan.user_id == user_id)
    stmt2 = delete(Session).where(Session.plan_id == plan_id, Session.user_id == user_id)
    async with db.begin():
        await db.execute(stmt2)
        await db.execute(stmt)
    return

async def update_plan_by_id(db, plan, *, user_id: int):
    await ensure_owned_plan(db, plan.id, user_id=user_id)
    stmt = update(Plan).where(Plan.id == plan.id, Plan.user_id == user_id).values(name=plan.name)
    await db.execute(stmt)
    await db.commit()
    return 
