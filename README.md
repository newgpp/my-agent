# my-agent
MCP-Powered Work Assistant Agent

## Requirements
- Python 3.12
- Node.js (for filesystem MCP server via npx)
  - Note: `npx` needs network access to npm registry on first run.

## Setup
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Create `.env` from `.env.example` and fill in keys:
- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`
- `OCR_API_URL`
- `OCR_API_TOKEN`
- `FS_ALLOWED_DIR_1` (required)
- `FS_ALLOWED_DIR_2` (optional)
- `APP_HOST` (optional, default `127.0.0.1`)
- `APP_PORT` (optional, default `8000`)

## Run
```bash
python -m app.main
```

Server will be available at `http://127.0.0.1:8000`.

## MCP servers
MCP servers are started automatically by the app using `mcp_servers.json`.

Manual start commands (for debugging):
```bash
# Filesystem MCP server (uses allowed dirs)
npx -y @modelcontextprotocol/server-filesystem "$FS_ALLOWED_DIR_1" "$FS_ALLOWED_DIR_2"

# Tavily MCP server (local Python)
.venv/bin/python servers/tavily_mcp_server.py
```

## Test (SSE)
```bash
# NOTE: Use URL encoding for non-ASCII query strings.
curl -G -N --data-urlencode "message=列出Downloads前10个文件" "http://127.0.0.1:8000/v1/chat/sse"
curl -G -N --data-urlencode "message=用tavily搜索旧金山今天天气" "http://127.0.0.1:8000/v1/chat/sse"
```

## Network checks
If tool calls fail, verify network access:

```bash
# DeepSeek API
curl -I https://api.deepseek.com

# Tavily API
curl -I https://api.tavily.com

# OCR API (replace with your endpoint)
curl -I "$OCR_API_URL"
```
