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