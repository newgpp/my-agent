import json
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from app.llm.deepseek_client import DeepSeekClient
from app.mcp.runner import MCPRunner
from app.mcp.tool_adapter import build_openai_tools, tool_result_to_text


def _get_tool_calls(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool calls from a chat completion response."""
    choices = response.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    return tool_calls


def _assistant_message_from_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the assistant message from a chat completion response."""
    choices = response.get("choices") or []
    if not choices:
        return {"role": "assistant", "content": ""}
    message = choices[0].get("message") or {}
    return message


def _parse_tool_args(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Parse tool call arguments into a dict."""
    fn = tool_call.get("function") or {}
    raw_args = fn.get("arguments") or "{}"
    if isinstance(raw_args, dict):
        return raw_args
    try:
        return json.loads(raw_args)
    except json.JSONDecodeError:
        return {}


def _select_tool_choice(user_message: str, tool_names: List[str]) -> Optional[Dict[str, Any]]:
    """Heuristic tool_choice for common filesystem/search requests."""
    lower = user_message.lower()
    if ("tavily" in lower or "搜索" in user_message) and "tavily_search" in tool_names:
        return {"type": "function", "function": {"name": "tavily_search"}}
    if (
        ("downloads" in lower or "下载" in user_message)
        and ("列出" in user_message or "list" in lower or "show" in lower)
        and "list_directory" in tool_names
    ):
        return {"type": "function", "function": {"name": "list_directory"}}
    return None


async def _run_tools(
    tool_calls: List[Dict[str, Any]],
    runner: MCPRunner,
    tool_name_to_server: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Execute tool calls and return tool role messages."""
    tool_messages: List[Dict[str, Any]] = []
    for call in tool_calls:
        fn = call.get("function") or {}
        tool_name = fn.get("name")
        if not tool_name:
            continue
        server = tool_name_to_server.get(tool_name)
        if not server:
            raise RuntimeError(f"Unknown tool: {tool_name}")
        args = _parse_tool_args(call)
        logger.info("Executing tool {} on {}", tool_name, server)
        result = await runner.call_tool(server, tool_name, args)
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": tool_result_to_text(result),
            }
        )
    return tool_messages


async def build_final_messages(
    user_message: str,
    runner: MCPRunner,
    client: DeepSeekClient,
    max_rounds: int = 5,
) -> List[Dict[str, Any]]:
    """Run tool-calling loop and return final messages for streaming."""
    tools_by_server = await runner.list_tools()
    tools, tool_name_to_server = build_openai_tools(tools_by_server)
    tool_choice = _select_tool_choice(user_message, list(tool_name_to_server.keys()))

    messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

    for i in range(max_rounds):
        logger.info("Tool loop round {}", len(messages))
        choice = tool_choice if i == 0 else "auto"
        response = await client.chat(messages, tools=tools, tool_choice=choice)
        tool_calls = _get_tool_calls(response)
        if not tool_calls:
            return messages

        assistant_message = _assistant_message_from_response(response)
        messages.append(assistant_message)
        tool_messages = await _run_tools(tool_calls, runner, tool_name_to_server)
        messages.extend(tool_messages)

    return messages


async def stream_final_answer(
    messages: List[Dict[str, Any]],
    client: DeepSeekClient,
) -> AsyncIterator[str]:
    """Stream only the final answer tokens."""
    async for chunk in client.stream_chat(messages):
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            yield text
