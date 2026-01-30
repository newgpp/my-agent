# SPEC - Non-negotiables

## Runtime
- Python 3.12
- FastAPI + SSE (text/event-stream)
- DeepSeek ChatCompletions API
- MCP Python SDK
- filesystem MCP server via npx @modelcontextprotocol/server-filesystem
- tavily MCP server (local python) that exposes a tool "tavily_search"

## SSE contract
- event: token  data: {"text": "..."}
- event: ping   data: {}
- event: error  data: {"message": "..."}
- event: done   data: {}

## Agent behavior
- Tool calling MUST happen in non-stream step
- Only final answer is streamed
- Tool results MUST be appended as role="tool" messages

## Security
- filesystem tools ONLY operate inside allowed dirs
- allowed dirs from env FS_ALLOWED_DIR_1/2
