# DEV_NOTES - MCP-Powered Work Assistant (FastAPI + SSE + DeepSeek + MCP)

> 目标：今天跑通 “用户提问 -> Agent -> DeepSeek -> MCP 工具 -> DeepSeek -> SSE 输出” 闭环

## 0. 关键依赖与约束

- Python: 3.12
- Web: FastAPI + SSE（`text/event-stream`）
- LLM: DeepSeek-V3.2（OpenAI 风格 `/chat/completions`；支持 `stream: true`，以 `data: [DONE]` 结束）  
- MCP:
  - Filesystem MCP Server：用 `npx -y @modelcontextprotocol/server-filesystem <allowed_dir...>` 跑（只允许操作传入目录，首次运行需要联网拉包）  
  - Tavily：今天用 “自建 Tavily MCP Server（Python）” 包一层，保持 MCP 一致性（后续可替换为社区 Tavily MCP）

参考：
- DeepSeek Chat Completions: `POST /chat/completions`；`stream: true` 用 SSE chunk 返回 :contentReference[oaicite:1]{index=1}  
- Tavily API：`POST https://api.tavily.com/search`（Bearer Key） :contentReference[oaicite:2]{index=2}  
- Filesystem MCP Server（npx 配置示例；args 指定 allowed dirs）:contentReference[oaicite:3]{index=3}  

---

## 1. 环境变量

创建 `.env`（参考 `.env.example`）：

- `DEEPSEEK_API_KEY=...`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`   # 如需 beta 特性再改
- `DEEPSEEK_MODEL=deepseek-chat`                 # 或 deepseek-reasoner
- `TAVILY_API_KEY=tvly-...`
- `FS_ALLOWED_DIR_1=/Users/<you>/Downloads`      # 你允许 agent 操作的目录
- `FS_ALLOWED_DIR_2=/Users/<you>/Desktop`        # 可选
- `APP_HOST=127.0.0.1`
- `APP_PORT=8000`

---

## 1.1 重要提示（curl 非 ASCII）
直接在 URL 中使用中文参数会导致 Uvicorn 返回 400。请使用 URL 编码：

```bash
curl -G -N --data-urlencode "message=列出Downloads前10个文件" "http://127.0.0.1:8000/v1/chat/sse"
curl -G -N --data-urlencode "message=用tavily搜索旧金山今天天气" "http://127.0.0.1:8000/v1/chat/sse"
```

## 2. 安装与启动（今天就按这个走）

### 2.1 Python 依赖

```bash
cd my-agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 2.2 启动

```bash
# 方式一：python 启动（读取 .env）
python -m app.main

# 方式二：uvicorn（推荐；便于看日志）
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## 今日收尾（2026-01-31）

已完成：
- FastAPI SSE 接口可用，事件契约满足 `token/ping/error/done`
- MCP filesystem + tavily 服务可用，MCP roots 正确下发
- DeepSeek 非流式工具调用 + 最终流式输出闭环跑通
- 处理了工具结果序列化、Uvicorn 事件与 URL 编码问题
- LLM / MCP 输入输出日志已打印

已验证（通过 URL 编码调用）：
- `GET /v1/chat/sse?message=列出Downloads前10个文件`
- `GET /v1/chat/sse?message=用tavily搜索旧金山今天天气`

注意：
- curl 直接携带中文参数会返回 400，请用 `--data-urlencode`
- 如果遇到 MCP 文件系统无法列目录，检查 `FS_ALLOWED_DIR_1/2` 是否正确
