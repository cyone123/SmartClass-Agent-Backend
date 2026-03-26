from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def success_response(
    data: Any = None,
    message: str = "success",
    response_model: type[BaseModel] | None = None,
):
    payload = {
        "code": 0,
        "message": message,
        "data": data,
    }
    if response_model is None:
        return payload
    return response_model(**payload)


class BaseResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="Response code")
    message: str = Field(default="success", description="Response message")
    data: T = Field(..., description="Response payload")
