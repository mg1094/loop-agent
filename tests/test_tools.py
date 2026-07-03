import json
import pytest
from loop_agent.agent.tools import BaseTool, ToolRegistry


class AddTool(BaseTool):
    name = "add"
    description = "Add two numbers."
    parameters = {
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    }

    def execute(self, *, a: float, b: float) -> str:
        return json.dumps({"result": a + b})


def test_registry_register_and_get():
    registry = ToolRegistry()
    tool = AddTool()
    registry.register(tool)
    assert registry.get("add") is tool


def test_registry_get_definitions():
    registry = ToolRegistry()
    registry.register(AddTool())
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0]["function"]["name"] == "add"


def test_registry_execute():
    registry = ToolRegistry()
    registry.register(AddTool())
    result = registry.execute("add", {"a": 1, "b": 2})
    assert json.loads(result)["result"] == 3


def test_registry_execute_missing_tool():
    registry = ToolRegistry()
    result = registry.execute("missing", {})
    data = json.loads(result)
    assert data["status"] == "error"
