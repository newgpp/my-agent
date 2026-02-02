# DEV_NOTES - MCP-Powered Work Assistant (FastAPI + SSE + DeepSeek + MCP)

目标：跑通“用户提问 -> Agent -> DeepSeek -> MCP 工具 -> DeepSeek -> SSE 输出”闭环。

## 关键依赖与约束

- Python: 3.12
- Web: FastAPI + SSE（`text/event-stream`）
- LLM: DeepSeek（OpenAI 风格 `/chat/completions`，支持 `stream: true`）
- MCP:
  - Filesystem MCP Server：`npx -y @modelcontextprotocol/server-filesystem <allowed_dir...>`
  - Tavily：自建 Tavily MCP Server（Python）

## 环境变量

创建 `.env`（参考 `.env.example`）：

- `DEEPSEEK_API_KEY=...`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-chat`
- `TAVILY_API_KEY=tvly-...`
- `FS_ALLOWED_DIR_1=/Users/<you>/Downloads`
- `FS_ALLOWED_DIR_2=/Users/<you>/Desktop`
- `APP_HOST=127.0.0.1`
- `APP_PORT=8000`

## 提示

URL 参数包含中文时请使用 URL 编码，避免 400：

```bash
curl -G -N --data-urlencode "message=列出Downloads前10个文件" "http://127.0.0.1:8000/v1/chat/sse"
```

## 安装与启动

```bash
cd my-agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

python -m app.main
# 或
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Agent 分层设计（当前）

1) 意图识别层（Planner）
   - 输入：用户 message + 可用工具摘要 + FS roots
   - 输出：固定 JSON（intent / route / tool_calls / final_user_message）
   - 目的：最低 token 成本完成“意图 + 工具决策”

2) 路由上下文选择（Route Context）
   - 不同意图映射到不同 system prompt + tool allowlist
   - file_list：仅 list_directory / read_file
   - external_knowledge：仅 tavily_search
   - sql_generate：提示用户走 /v1/sql/sse（chat 路由不直接产 SQL）

3) 工具执行层（Tool Runner）
   - 仅执行 Planner 输出的 tool_calls
   - 执行结果整理为 TOOL_RESULTS，作为下游输入

4) 结果合成层（Final LLM）
   - system：route prompt
   - user：原始或重写后的 message
   - system：TOOL_RESULTS（若有）
   - 输出：最终自然语言结果（SSE 仅输出 text）

5) SQL 路由（/v1/sql/sse）
   - 独立接口，但复用统一上下文：
     - prompt：text_to_sql
     - resources：db_schema + business_glossary
   - 输出：严格 SQL（含校验）
