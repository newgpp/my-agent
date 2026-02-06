import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.agent.loop import build_final_messages, stream_final_answer
from app.llm.deepseek_client import DeepSeekClient
from app.mcp.runner import MCPRunner
from loguru import logger

router = APIRouter()


# def _sse_event(event: str, data: dict) -> str:
#     """Format a Server-Sent Events payload."""
#     return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Events payload."""
    return data.get("text", "")


def get_runner() -> MCPRunner:
    """Return the global MCP runner instance."""
    from app.main import mcp_runner

    return mcp_runner


def get_client() -> DeepSeekClient:
    """Create a DeepSeek client for the request."""
    return DeepSeekClient()


@router.get("/v1/chat/sse")
async def chat_sse(
    message: str = Query(...),
    runner: MCPRunner = Depends(get_runner),
    client: DeepSeekClient = Depends(get_client),
) -> StreamingResponse:
    """SSE endpoint for chat streaming with tool execution."""

    async def event_stream() -> AsyncIterator[str]:
        try:
            logger.info("SSE request received message_len={}", len(message))
            messages = await build_final_messages(message, runner, client)
            last_ping = asyncio.get_running_loop().time()
            async for token in stream_final_answer(messages, client):
                now = asyncio.get_running_loop().time()
                if now - last_ping >= 10:
                    yield _sse_event("ping", {})
                    last_ping = now
                yield _sse_event("token", {"text": token})
            yield _sse_event("done", {})
        except Exception as exc:
            logger.exception("SSE request failed")
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
