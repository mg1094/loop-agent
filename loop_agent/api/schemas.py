from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt")


class ChatResponse(BaseModel):
    status: str
    content: str
    run_id: str
    run_dir: str


class SkillsResponse(BaseModel):
    descriptions: str


class ToolsResponse(BaseModel):
    tools: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str