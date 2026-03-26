from pydantic import BaseModel, ConfigDict

from app.schemas.response import BaseResponse


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    thread_id: str
    plan_id: int

class SessionResponse(BaseResponse[Session]):
    pass

class SessionRequest(BaseModel):
    name: str
    plan_id: int

class Messages(BaseModel):
    messages: list[dict]

class MessagesResponse(BaseResponse[Messages]):
    pass