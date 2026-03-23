"""Pydantic models for chat API"""
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    model_id: str = "gpt-4o"
    session_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    content: str
    model_id: str
    session_id: str


class ErrorResponse(BaseModel):
    detail: str
