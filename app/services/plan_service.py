from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from app.models.plan import Plan
from app.models.session import Session

async def get_plan(db):
    query = (
        select(Plan)
        .options(selectinload(Plan.sessions))
        .order_by(Plan.id.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def create_plan(db, name):
    new_plan = Plan(name=name)
    db.add(new_plan)
    await db.commit()
    await db.refresh(new_plan)
    return new_plan

async def delete_plan_by_id(db, plan_id):
    stmt = delete(Plan).where(Plan.id == plan_id)
    stmt2 = delete(Session).where(Session.plan_id == plan_id)
    async with db.begin():
        await db.execute(stmt2)
        await db.execute(stmt)
    return

async def update_plan_by_id(db, plan):
    stmt = update(Plan).where(Plan.id == plan.id).values(name=plan.name)
    await db.execute(stmt)
    await db.commit()
    return 