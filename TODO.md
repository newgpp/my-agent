# TODO - Today MVP (must run)

## Goal
Build MCP-powered work assistant with FastAPI SSE chat:
User -> Agent -> DeepSeek -> (optional MCP tool calls: filesystem/tavily) -> DeepSeek -> SSE stream final answer.

## Must-have deliverables (today)
1. FastAPI app runs on http://127.0.0.1:8000
2. GET /v1/chat/sse?message=... returns SSE stream (token events + done)
3. MCP filesystem tool works (list/read within allowed dirs)
4. MCP tavily tool works (search web and return results)
5. Agent loop:
   - first call DeepSeek non-stream
   - if tool_calls -> execute tools -> feed tool results -> repeat
   - final answer call DeepSeek stream and forward to SSE

## Files to implement
- app/main.py
- app/api/chat.py
- app/agent/loop.py
- app/llm/deepseek_client.py
- app/mcp/registry.py
- app/mcp/tool_adapter.py
- app/mcp/runner.py
- servers/tavily_mcp_server.py
- requirements.txt
- mcp_servers.json
- .env.example

## Acceptance tests
- curl -N "http://127.0.0.1:8000/v1/chat/sse?message=列出Downloads前10个文件"
- curl -N "http://127.0.0.1:8000/v1/chat/sse?message=用tavily搜索旧金山今天天气"
