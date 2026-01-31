import json
from typing import Any, Dict, List, Tuple

from loguru import logger

from app.mcp.schemas import MCPTool, OpenAIFunction, OpenAITool, ToolResultContent

def _tool_to_openai(tool: Any, server_name: str) -> Dict[str, Any]:
    """Convert an MCP tool to OpenAI tools format."""
    mcp_tool = (
        MCPTool.model_validate(tool)
        if isinstance(tool, dict)
        else MCPTool.model_validate(
            {"name": getattr(tool, "name", None), "description": getattr(tool, "description", None), "inputSchema": getattr(tool, "inputSchema", None) or {}}
        )
    )

    oa_tool = OpenAITool(
        function=OpenAIFunction(
            name=mcp_tool.name,
            description=mcp_tool.description,
            parameters=mcp_tool.input_schema,
        ),
        x_mcp_server=server_name,
    )
    return oa_tool.model_dump(by_alias=True, exclude_none=True)


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
        return json.dumps(ToolResultContent.model_validate(result).model_dump(exclude_none=True), ensure_ascii=False)
    if hasattr(result, "content"):
        payload = ToolResultContent(
            content=getattr(result, "content", None),
            is_error=getattr(result, "is_error", None),
        )
        return json.dumps(payload.model_dump(exclude_none=True), ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
