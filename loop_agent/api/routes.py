from __future__ import annotations

from fastapi import APIRouter

from loop_agent import __version__
from loop_agent.api.schemas import HealthResponse, SkillsResponse, ToolsResponse
from loop_agent.cli.commands import list_skills, list_tool_names

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
