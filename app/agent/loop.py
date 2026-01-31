import json
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from app.agent.schemas import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    ChatMessage,
    ToolCall,
)
from app.config import get_settings
from app.llm.deepseek_client import DeepSeekClient
from app.mcp.runner import MCPRunner
from app.mcp.tool_adapter import build_openai_tools, tool_result_to_text


def _get_tool_calls(response: Dict[str, Any]) -> List[ToolCall]:
    """Extract tool calls from a chat completion response."""
    parsed = ChatCompletionResponse.model_validate(response)
    if not parsed.choices:
        return []
    return parsed.choices[0].message.tool_calls or []


def _assistant_message_from_response(response: Dict[str, Any]) -> ChatMessage:
    """Extract the assistant message from a chat completion response."""
    parsed = ChatCompletionResponse.model_validate(response)
    if not parsed.choices:
        return ChatMessage(role="assistant", content="")
    return parsed.choices[0].message


def _parse_tool_args(tool_call: ToolCall) -> Dict[str, Any]:
    """Parse tool call arguments into a dict."""
    fn = tool_call.function
    raw_args = fn.arguments if fn else "{}"
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
    tool_calls: List[ToolCall],
    runner: MCPRunner,
    tool_name_to_server: Dict[str, str],
) -> List[ChatMessage]:
    """Execute tool calls and return tool role messages."""
    tool_messages: List[ChatMessage] = []
    for call in tool_calls:
        fn = call.function
        tool_name = fn.name if fn else None
        if not tool_name:
            continue
        server = tool_name_to_server.get(tool_name)
        if not server:
            raise RuntimeError(f"Unknown tool: {tool_name}")
        args = _parse_tool_args(call)
        logger.info("Executing tool {} on {}", tool_name, server)
        result = await runner.call_tool(server, tool_name, args)
        tool_messages.append(
            ChatMessage(
                role="tool",
                tool_call_id=call.id,
                content=tool_result_to_text(result),
            )
        )
    return tool_messages


def _dump_messages(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    return [message.model_dump(exclude_none=True) for message in messages]


async def build_final_messages(
    user_message: str,
    runner: MCPRunner,
    client: DeepSeekClient,
    max_rounds: int = 5,
) -> List[ChatMessage]:
    """Run tool-calling loop and return final messages for streaming."""
    tools_by_server = await runner.list_tools()
    tools, tool_name_to_server = build_openai_tools(tools_by_server)
    tool_choice = _select_tool_choice(user_message, list(tool_name_to_server.keys()))

    messages: List[ChatMessage] = []
    roots = get_settings().fs_roots()
    if roots:
        messages.append(
            ChatMessage(
                role="system",
                content=(
                    "Filesystem tools can only access these allowed directories. "
                    "Use absolute paths and prefer these roots when calling file tools:\n"
                    + "\n".join(roots)
                ),
            )
        )
    messages.append(ChatMessage(role="user", content=user_message))

    for i in range(max_rounds):
        logger.info("Tool loop round {}", len(messages))
        choice = tool_choice if i == 0 else "auto"
        response = await client.chat(_dump_messages(messages), tools=tools, tool_choice=choice)
        tool_calls = _get_tool_calls(response)
        if not tool_calls:
            return messages

        assistant_message = _assistant_message_from_response(response)
        messages.append(assistant_message)
        tool_messages = await _run_tools(tool_calls, runner, tool_name_to_server)
        messages.extend(tool_messages)

    return messages


async def stream_final_answer(
    messages: List[ChatMessage],
    client: DeepSeekClient,
) -> AsyncIterator[str]:
    """Stream only the final answer tokens."""
    async for chunk in client.stream_chat(_dump_messages(messages)):
        parsed = ChatCompletionChunk.model_validate(chunk)
        if not parsed.choices:
            continue
        text = parsed.choices[0].delta.content
        if text:
            yield text
