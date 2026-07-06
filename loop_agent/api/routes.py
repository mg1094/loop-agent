from __future__ import annotations

from fastapi import APIRouter, HTTPException

from loop_agent import __version__
from loop_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SkillsResponse,
    ToolsResponse,
)
from loop_agent.cli.commands import _run_agent, list_skills, list_tool_names

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/skills", response_model=SkillsResponse)
def skills() -> SkillsResponse:
    return SkillsResponse(descriptions=list_skills())


@router.get("/tools", response_model=ToolsResponse)
def tools() -> ToolsResponse:
    return ToolsResponse(tools=list_tool_names())


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be blank")
    result = _run_agent(req.prompt, session_id=req.session_id)
    return ChatResponse(
        status=result["status"],
        content=result["content"],
        run_id=result["run_id"],
        run_dir=result["run_dir"],
        session_id=req.session_id,
    )
