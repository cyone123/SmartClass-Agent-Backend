from __future__ import annotations

from sqlalchemy import delete, select, update
from uuid_utils import uuid4
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.models.session import Session


async def get_session_list_by_plan(db, plan_id):
    query = select(Session).where(Session.plan_id == plan_id)
    result = await db.execute(query)
    return result.scalars().all()


async def create_session(db, name, plan_id):
    thread_id = uuid4().hex
    new_session = Session(name=name, plan_id=plan_id, thread_id=thread_id)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session


async def get_session_by_thread_id(db, thread_id):
    query = select(Session).where(Session.thread_id == thread_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


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


async def delete_session_by_id(db, session_id):
    stmt = delete(Session).where(Session.id == session_id)
    await db.execute(stmt)
    # TODO: 鍒犻櫎浼氳瘽鍐呯殑鍘嗗彶娑堟伅
    return


async def update_session_by_id(db, session):
    stmt = update(Session).where(Session.id == session.id).values(name=session.name)
    await db.execute(stmt)
    await db.commit()
    return
