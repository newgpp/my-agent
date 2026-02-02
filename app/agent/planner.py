from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field, ConfigDict

from app.config import get_settings
from app.llm.deepseek_client import DeepSeekClient
from app.mcp.schemas import MCPTool
from app.prompts.loader import load_prompt


class PlannerToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    arguments: Any = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: str = "external_knowledge"
    route: str = "external_knowledge"
    tool_calls: List[PlannerToolCall] = Field(default_factory=list)
    final_user_message: Optional[str] = None


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _summarize_tools(tools_by_server: Dict[str, List[Any]]) -> List[str]:
    summaries: List[str] = []
    for server_tools in tools_by_server.values():
        for tool in server_tools:
            mcp_tool = MCPTool.model_validate(tool) if isinstance(tool, dict) else MCPTool.model_validate(
                {
                    "name": getattr(tool, "name", None),
                    "description": getattr(tool, "description", None),
                    "inputSchema": getattr(tool, "inputSchema", None) or {},
                }
            )
            if not mcp_tool.name:
                continue
            description = mcp_tool.description or ""
            if description:
                summaries.append(f"{mcp_tool.name}: {description}")
            else:
                summaries.append(mcp_tool.name)
    return summaries


def _build_planner_prompt(tools_by_server: Dict[str, List[Any]]) -> str:
    base_prompt = load_prompt("chat_planner")
    tool_summaries = _summarize_tools(tools_by_server)
    roots = get_settings().fs_roots()

    parts = [base_prompt.strip()]
    if tool_summaries:
        parts.append("AVAILABLE_TOOLS:")
        parts.extend(f"- {line}" for line in tool_summaries)
    if roots:
        parts.append("FS_ROOTS:")
        parts.extend(f"- {root}" for root in roots)
    return "\n".join(parts)


async def run_planner(
    user_message: str,
    tools_by_server: Dict[str, List[Any]],
    client: DeepSeekClient,
) -> PlannerOutput:
    prompt = _build_planner_prompt(tools_by_server)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_message},
    ]
    response = await client.chat(messages, temperature=0.1)
    choices = response.get("choices") or []
    if not choices:
        logger.warning("Planner response missing choices; using defaults")
        return PlannerOutput()
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    payload = _extract_json(content)
    try:
        return PlannerOutput.model_validate(payload)
    except Exception:
        logger.exception("Planner output invalid; using defaults")
        return PlannerOutput()
