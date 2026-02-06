import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from loguru import logger

from app.agent.routes import get_sql_route_context
from app.llm.deepseek_client import DeepSeekClient
from app.sql.validator import validate_sql, contains_forbidden_keyword

router = APIRouter()


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Events payload."""
    return data.get("text", "")


def get_client() -> DeepSeekClient:
    """Create a DeepSeek client for the request."""
    return DeepSeekClient()


@router.get("/v1/sql/sse")
async def sql_sse(
    message: str = Query(...),
    client: DeepSeekClient = Depends(get_client),
) -> StreamingResponse:
    """SSE endpoint for text-to-sql generation."""

    async def event_stream() -> AsyncIterator[str]:
        try:
            logger.info("SQL SSE request received message_len={}", len(message))
            if contains_forbidden_keyword(message):
                ok, reason = validate_sql(message)
                if not ok:
                    yield _sse_event("error", {"text": f"ERROR: {reason}"})
                    yield _sse_event("done", {})
                    return
            route_context = get_sql_route_context()
            messages = [{"role": "system", "content": route_context.system_prompt}]
            for extra in route_context.extra_system_messages:
                messages.append({"role": "system", "content": extra})
            messages.append({"role": "user", "content": message})

            response = await client.chat(messages)
            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError("LLM response missing choices")
            message = choices[0].get("message") or {}
            sql_text = (message.get("content") or "").strip()
            if not sql_text:
                raise RuntimeError("LLM returned empty SQL")

            ok, reason = validate_sql(sql_text)
            if not ok:
                yield _sse_event("error", {"text": f"ERROR: {reason}"})
                yield _sse_event("done", {})
                return

            last_ping = asyncio.get_running_loop().time()
            for chunk in sql_text.splitlines(keepends=True):
                now = asyncio.get_running_loop().time()
                if now - last_ping >= 10:
                    yield _sse_event("ping", {})
                    last_ping = now
                yield _sse_event("token", {"text": chunk})
            if not sql_text.endswith("\n"):
                yield _sse_event("token", {"text": ""})
            yield _sse_event("done", {})
        except Exception as exc:
            logger.exception("SQL SSE request failed")
            yield _sse_event("error", {"text": f"ERROR: {exc}"})
            yield _sse_event("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
