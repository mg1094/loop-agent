from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt")
    session_id: str = Field(default="", max_length=256, description="Optional session ID")


class ChatResponse(BaseModel):
    status: str
    content: str
    run_id: str
    run_dir: str
    session_id: str = ""


class SkillsResponse(BaseModel):
    descriptions: str


class ToolsResponse(BaseModel):
    tools: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: list[dict]


class SessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool


class SessionSummary(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SearchHit(BaseModel):
    session_id: str
    updated_at: str
    match_count: int


class SessionSearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
