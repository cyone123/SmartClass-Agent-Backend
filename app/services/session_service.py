from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from uuid_utils import uuid4
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.models.session import Session
from app.services.plan_service import ensure_owned_plan


async def get_session_list_by_plan(db, plan_id, *, user_id: int):
    await ensure_owned_plan(db, plan_id, user_id=user_id)
    query = select(Session).where(Session.plan_id == plan_id, Session.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


async def create_session(db, name, plan_id, *, user_id: int):
    await ensure_owned_plan(db, plan_id, user_id=user_id)
    thread_id = uuid4().hex
    new_session = Session(name=name, plan_id=plan_id, thread_id=thread_id, user_id=user_id)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session


async def get_session_by_thread_id(db, thread_id, *, user_id: int | None = None):
    query = select(Session).where(Session.thread_id == thread_id)
    if user_id is not None:
        query = query.where(Session.user_id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def ensure_owned_session_by_thread_id(db, thread_id: str, *, user_id: int) -> Session:
    session = await get_session_by_thread_id(db, thread_id, user_id=user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found.",
        )
    return session

async def ensure_owned_session_by_id(db, session_id: int, *, user_id: int) -> Session:
    stmt = select(Session).where(Session.id == session_id, Session.user_id == user_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )
    return session


async def get_message_histry(thread_id, agent_runtime):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await agent_runtime.graph.aget_state(config)
    messages = state_snapshot.values.get("messages", None)

    messages_res = []
    if messages is None:
        messages = []

    for msg in messages:
        if isinstance(msg, (ToolMessage, SystemMessage)):
            continue
        messages_res.append(
            {
                "role": "teacher" if isinstance(msg, HumanMessage) else "ai",
                "type": "text",
                "content": msg.content,
            }
        )

    pending_approval = await agent_runtime.get_pending_approval(thread_id)
    if pending_approval:
        messages_res.append(
            {
                "role": "ai",
                "type": "approval-card",
                "approval": pending_approval,
                "state": "pending",
            }
        )
    return messages_res


async def delete_session_by_id(db, session_id, *, user_id: int):
    await ensure_owned_session_by_id(db, session_id, user_id=user_id)
    stmt = delete(Session).where(Session.id == session_id, Session.user_id == user_id)
    await db.execute(stmt)
    # TODO: 鍒犻櫎浼氳瘽鍐呯殑鍘嗗彶娑堟伅
    return


async def update_session_by_id(db, session, *, user_id: int):
    await ensure_owned_session_by_id(db, session.id, user_id=user_id)
    stmt = update(Session).where(Session.id == session.id, Session.user_id == user_id).values(name=session.name)
    await db.execute(stmt)
    await db.commit()
    return
