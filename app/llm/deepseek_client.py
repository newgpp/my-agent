import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        """Initialize DeepSeek client with env-based defaults."""
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        logger.info("DeepSeek client initialized model={}", self.model)

    def _headers(self) -> Dict[str, str]:
        """HTTP headers for DeepSeek API."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self) -> str:
        """Build chat completions endpoint URL."""
        return f"{self.base_url}/chat/completions"

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Run a non-streaming chat completion."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.info("DeepSeek chat request messages={} tools={}", len(messages), bool(tools))
            resp = await client.post(self._url(), headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.json()

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a chat completion and yield parsed SSE chunks."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.info("DeepSeek stream request messages={} tools={}", len(messages), bool(tools))
            async with client.stream("POST", self._url(), headers=self._headers(), json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue
