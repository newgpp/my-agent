import os
from datetime import timedelta
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any, Dict, List

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
import mcp.types as types

from app.mcp.registry import MCPServerConfig, load_mcp_servers
from loguru import logger


def _extract_tools(result: Any) -> List[Any]:
    """Normalize list_tools output across SDK versions."""
    if isinstance(result, dict) and "tools" in result:
        return result["tools"]
    if hasattr(result, "tools"):
        return result.tools
    return result


class MCPClientSession(ClientSession):
    def __init__(self, read_stream, write_stream, roots: List[str]) -> None:
        super().__init__(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=30))
        self._roots = roots

    async def _received_request(self, responder) -> None:
        request = responder.request.root
        if isinstance(request, types.ListRootsRequest):
            roots = []
            for path in self._roots:
                try:
                    uri = Path(path).resolve().as_uri()
                except ValueError:
                    continue
                roots.append(types.Root(uri=types.FileUrl(uri), name=Path(path).name))
            await responder.respond(types.ClientResult(types.ListRootsResult(roots=roots)))


class MCPRunner:
    def __init__(self, config_path: str = "mcp_servers.json") -> None:
        """Create MCP runner for configured servers."""
        self._config_path = config_path
        self._servers: Dict[str, MCPServerConfig] = {}
        self._sessions: Dict[str, ClientSession] = {}
        self._stack = AsyncExitStack()
        self._roots = self._load_roots()

    @staticmethod
    def _load_roots() -> List[str]:
        roots = []
        for key in ("FS_ALLOWED_DIR_1", "FS_ALLOWED_DIR_2"):
            value = os.getenv(key)
            if value:
                roots.append(value)
        return roots

    async def start(self) -> None:
        """Start all MCP servers and initialize sessions."""
        self._servers = load_mcp_servers(self._config_path)
        for name, cfg in self._servers.items():
            logger.info("Starting MCP server {} command={} args={}", name, cfg.command, cfg.args)
            params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args,
                env={**os.environ, **(cfg.env or {})},
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(MCPClientSession(read, write, self._roots))
            await session.initialize()
            self._sessions[name] = session
            logger.info("MCP server started {}", name)

    async def close(self) -> None:
        """Close all MCP sessions."""
        await self._stack.aclose()
        self._sessions = {}
        logger.info("MCP runner closed")

    async def list_tools(self) -> Dict[str, List[Any]]:
        """List tools from all MCP servers."""
        tools_by_server: Dict[str, List[Any]] = {}
        for name, session in self._sessions.items():
            result = await session.list_tools()
            tools_by_server[name] = _extract_tools(result)
        return tools_by_server

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on a specific MCP server."""
        if server_name not in self._sessions:
            raise RuntimeError(f"MCP server not started: {server_name}")
        session = self._sessions[server_name]
        logger.info("Calling tool {} on {}", tool_name, server_name)
        return await session.call_tool(tool_name, arguments)
