import json
from typing import Any, Dict, List, Tuple

from loguru import logger

def _tool_to_openai(tool: Any, server_name: str) -> Dict[str, Any]:
    """Convert an MCP tool to OpenAI tools format."""
    if isinstance(tool, dict):
        name = tool.get("name")
        description = tool.get("description")
        parameters = tool.get("inputSchema") or {}
    else:
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", None)
        parameters = getattr(tool, "inputSchema", None) or {}

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
        "x-mcp-server": server_name,
    }


def build_openai_tools(
    tools_by_server: Dict[str, List[Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Build OpenAI tools and a tool->server map."""
    tools: List[Dict[str, Any]] = []
    tool_name_to_server: Dict[str, str] = {}

    for server_name, server_tools in tools_by_server.items():
        for tool in server_tools:
            oa_tool = _tool_to_openai(tool, server_name)
            tools.append(oa_tool)
            tool_name = oa_tool["function"]["name"]
            if tool_name:
                tool_name_to_server[tool_name] = server_name
                logger.info("Registered tool {} from {}", tool_name, server_name)

    return tools, tool_name_to_server


def tool_result_to_text(result: Any) -> str:
    """Serialize MCP tool result to a JSON string."""
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(mode="json", by_alias=True, exclude_none=True), ensure_ascii=False)
    if isinstance(result, dict) and "content" in result:
        return json.dumps(result, ensure_ascii=False)
    if hasattr(result, "content"):
        payload = {
            "content": result.content,
        }
        if hasattr(result, "is_error"):
            payload["is_error"] = result.is_error
        return json.dumps(payload, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
