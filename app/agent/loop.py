import json
from typing import Any, AsyncIterator, Dict, List

from loguru import logger

from app.agent.planner import PlannerToolCall, run_planner
from app.agent.routes import get_route_context
from app.agent.schemas import ChatCompletionChunk, ChatMessage
from app.llm.deepseek_client import DeepSeekClient
from app.mcp.runner import MCPRunner
from app.mcp.tool_adapter import build_openai_tools, tool_result_to_text


def _filter_planned_tool_calls(
    tool_calls: List[PlannerToolCall],
    allowlist: set[str],
) -> List[PlannerToolCall]:
    if not allowlist:
        return []
    filtered: List[PlannerToolCall] = []
    for call in tool_calls:
        if not call.name or call.name not in allowlist:
            continue
        if call.arguments is None:
            call.arguments = {}
        if isinstance(call.arguments, str):
            try:
                call.arguments = json.loads(call.arguments)
            except json.JSONDecodeError:
                call.arguments = {}
        filtered.append(call)
    return filtered


async def _run_planned_tools(
    tool_calls: List[PlannerToolCall],
    runner: MCPRunner,
    tool_name_to_server: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Execute planned tool calls and return tool output payloads."""
    tool_outputs: List[Dict[str, Any]] = []
    for call in tool_calls:
        tool_name = call.name
        if not tool_name:
            continue
        server = tool_name_to_server.get(tool_name)
        if not server:
            raise RuntimeError(f"Unknown tool: {tool_name}")
        args = call.arguments or {}
        logger.info("Executing tool {} on {}", tool_name, server)
        result = await runner.call_tool(server, tool_name, args)
        tool_outputs.append(
            {
                "name": tool_name,
                "arguments": args,
                "result": tool_result_to_text(result),
            }
        )
    return tool_outputs


def _format_tool_results(tool_outputs: List[Dict[str, Any]]) -> str:
    if not tool_outputs:
        return ""
    lines = ["TOOL_RESULTS:"]
    for output in tool_outputs:
        name = output.get("name", "unknown_tool")
        result = output.get("result", "")
        lines.append(f"[{name}] {result}")
    return "\n".join(lines)


def _dump_messages(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    return [message.model_dump(exclude_none=True) for message in messages]


async def build_final_messages(
    user_message: str,
    runner: MCPRunner,
    client: DeepSeekClient,
) -> List[ChatMessage]:
    """Plan, run tools once, and return final messages for streaming."""
    tools_by_server = await runner.list_tools()
    _, tool_name_to_server = build_openai_tools(tools_by_server)

    planner_output = await run_planner(user_message, tools_by_server, client)
    route_context = get_route_context(planner_output.route)
    planned_calls = _filter_planned_tool_calls(
        planner_output.tool_calls,
        set(route_context.tool_allowlist),
    )
    logger.info(
        "Planner intent={} route={} tools={}",
        planner_output.intent,
        planner_output.route,
        len(planned_calls),
    )
    tool_outputs = await _run_planned_tools(planned_calls, runner, tool_name_to_server)
    tool_result_text = _format_tool_results(tool_outputs)

    final_user_message = planner_output.final_user_message or user_message
    messages: List[ChatMessage] = [
        ChatMessage(role="system", content=route_context.system_prompt)
    ]
    for extra in route_context.extra_system_messages:
        messages.append(ChatMessage(role="system", content=extra))
    messages.append(ChatMessage(role="user", content=final_user_message))
    if tool_result_text:
        messages.append(ChatMessage(role="system", content=tool_result_text))
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
