import json

from loop_agent.agent.tools import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo the input message back. Useful for testing the tool loop."
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
        },
        "required": ["message"],
    }

    def execute(self, *, message: str) -> str:
        return json.dumps({"result": message}, ensure_ascii=False)
