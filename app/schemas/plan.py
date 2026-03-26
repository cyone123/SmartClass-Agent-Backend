
from typing import List

from pydantic import BaseModel, ConfigDict

from app.schemas.response import BaseResponse
from app.schemas.session import Session

class Plan(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    
class PlanRequest(BaseModel):
    name: str

class PlanResponse(BaseResponse[Plan]):
    pass

class PlanAndSessionList(Plan):
    model_config = ConfigDict(from_attributes=True)

    sessions: list[Session]

class PlanAndSessionListResponse(BaseResponse[List[PlanAndSessionList]]):
    pass

