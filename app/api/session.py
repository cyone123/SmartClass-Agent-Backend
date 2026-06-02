from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.services import session_service
from app.schemas.response import success_response
from app.schemas.response import success_response
from app.schemas.session import Session, SessionRequest, SessionRequest, SessionResponse, MessagesResponse, Messages
from app.core.agent import AgentRuntime, get_agent_runtime


router = APIRouter()

@router.put("/session", response_model=SessionResponse)
async def create_session(
    session_request: SessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    new_session = await session_service.create_session(
        db,
        session_request.name,
        session_request.plan_id,
        user_id=current_user.id,
    )
    return success_response(data=new_session, response_model=SessionResponse)


@router.get("/session/{thread_id}")
async def get_message_histry(thread_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    agent_runtime: AgentRuntime = Depends(get_agent_runtime),
) -> MessagesResponse:
    await session_service.ensure_owned_session_by_thread_id(db, thread_id, user_id=current_user.id)
    msgs = await session_service.get_message_histry(thread_id, agent_runtime)
    return success_response(data=Messages(messages=msgs), response_model=MessagesResponse)


@router.delete('/session/{session_id}')
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await session_service.delete_session_by_id(db, session_id, user_id=current_user.id)
    return success_response()


@router.post('/session')
async def update_session(
    session: Session,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await session_service.update_session_by_id(db, session, user_id=current_user.id)
    return success_response()
