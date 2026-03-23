from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户输入的消息")
    thread_id: Optional[str] = Field(None, description="会话ID，用于多轮对话")
    temperature: Optional[float] = Field(0.7, description="温度参数")
    stream: Optional[bool] = Field(False, description="是否流式输出")

class ChatResponse(BaseModel):
    thread_id: str
    response: str
    tokens_used: Optional[int] = None
    processing_time: float