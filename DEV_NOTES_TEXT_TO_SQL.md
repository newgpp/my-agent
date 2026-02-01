下面这份你可以直接覆盖/追加到 `DEV_NOTES.md`（或新建 `DEV_NOTES_TEXT_TO_SQL.md`），就是**“任务列表 + 验收标准 + Codex 执行顺序”**。我按你要求：**单段式、无外键、靠中文注释 join、只输出 SQL（允许 NEED_CLARIFY 注释）** 来写。

---

# DEV_NOTES - Text-to-SQL via MCP Resources + Prompts (Single-pass)

> 目标：今天跑通 `GET /v1/sql/sse?question=...`
> 流程：User Question → Agent loads Resources (db_schema + glossary) + Prompt (text_to_sql) → DeepSeek → SQL Safety Check → SSE 输出 SQL

## 0. 约束（必须严格遵守）

* **只做单段式**：一次 LLM 调用
* **只输出 SQL**：允许 SQL 注释；禁止输出解释性自然语言
* **禁止 DML/DDL**：INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE/CREATE
* **禁止多语句**：只允许 1 条 SELECT
* **禁止 SELECT ***：必须显式列字段
* **必须 LIMIT**：除非用户明确全量导出
* **DB 无外键**：JOIN 关系完全依赖 schema 的中文注释/规则描述
* 缺关键条件（时间范围/对象范围等）时：输出 `-- NEED_CLARIFY: ...` 注释 + 返回空结果 SQL（`WHERE 1=0 LIMIT 0`）
* **数据库框架使用SQLAlchemy**
---

## 1. 资源（Resources）落地

### 1.1 资源文件已存在（test_product_db.sql）

* [ ] 确认 schema 文件路径（示例）：

  * `resources/db_schema.sql`（无外键 + 中文注释明确 join）
* [ ] 新增业务口径文件：

  * `resources/business_glossary.md`（GMV=paid；活跃用户定义；金额分转元；时间字段口径）

### 1.2 Resource Provider（Agent 内部实现即可）

* [ ] 新增模块：`app/resources/provider.py`

  * `get_resource(uri: str) -> str`
  * uri 映射：

    * `context://db_schema` → `resources/db_schema.sql`
    * `context://business_glossary` → `resources/business_glossary.md`
  * 找不到资源：抛出明确异常（用于 SSE error 事件）

**验收**

* [ ] 本地调用 `get_resource("context://db_schema")` 返回非空
* [ ] `business_glossary` 可读，内容符合口径

---

## 2. Prompts 落地（Prompt Primitive）

### 2.1 Prompt 文件

* [ ] 新增 `prompts/text_to_sql.md`（单段式规则）

  * 只输出 SELECT
  * Join 仅能依据 db_schema 中文注释声明的字段
  * 默认口径：orders.order_status='paid'
  * 必须 LIMIT
  * 缺条件：输出 `-- NEED_CLARIFY:` 注释 + `SELECT ... WHERE 1=0 LIMIT 0`

### 2.2 Prompt Loader

* [ ] 新增模块：`app/prompts/loader.py`

  * `load_prompt(name: str) -> str`
  * `text_to_sql` → `prompts/text_to_sql.md`

**验收**

* [ ] `load_prompt("text_to_sql")` 返回非空

---

## 3. 单段式 Text-to-SQL 生成（DeepSeek）

### 3.1 组装 messages（重点）

* [ ] 新增模块：`app/sql/messages.py`

  * `build_text_to_sql_messages(question: str, db_schema: str, glossary: str, prompt: str) -> list[dict]`
* [ ] messages 结构建议：

  * system：prompt 规则（text_to_sql.md）
  * system：`context://db_schema` 内容（含 join 中文注释）
  * system：`context://business_glossary` 内容
  * user：question

> 注意：这里不要引入“第二次调用”，也不要把澄清交给另一个 prompt。

### 3.2 DeepSeek 调用

* [ ] 复用你现有 `deepseek_client`（/chat/completions）
* [ ] 先用**非流式**拿完整 SQL（更容易做安全校验），再把 SQL 以 SSE token 输出（你当前 SSE 事件契约已存在）

**验收**

* [ ] 对同一 question 能稳定生成 SQL（不是自然语言解释）

---

## 4. SQL 安全校验（强制）

### 4.1 实现校验器

* [ ] 新增模块：`app/sql/validator.py`

  * `validate_sql(sql: str) -> tuple[bool, str]`  (ok, reason)
* [ ] 校验规则（必须全做）：

  1. 去掉前导空白/注释后，必须以 `SELECT` 开头
  2. 禁止关键词（大小写不敏感）：INSERT/UPDATE/DELETE/ALTER/DROP/TRUNCATE/CREATE
  3. 禁止多语句：出现 `;` 后还有非空内容则拒绝（允许末尾单个分号也可选择拒绝/剥离）
  4. 禁止 `SELECT *`
  5. 必须包含 `LIMIT`（简单正则检测即可）

### 4.2 NEED_CLARIFY 检测（不二段式）

* [ ] 在 validator 前做一个轻量检查：

  * 若 SQL 顶部包含 `NEED_CLARIFY:` 注释：

    * 允许通过校验（只要仍是 SELECT 且安全）
    * SSE 输出时保留注释（UI 可解析）
* [ ] 若没有 NEED_CLARIFY 但缺少时间范围等（可选增强）：

  * 不在这里判断（避免再次智能化）；以 prompt 的输出为准

**验收**

* [ ] 故意让模型输出 DDL/DML 会被拦截并 SSE 返回 error
* [ ] `SELECT *` 被拦截
* [ ] 没 LIMIT 被拦截（或自动补 LIMIT —— 二选一；默认拦截更安全）

---

## 5. SSE 接口：`GET /v1/sql/sse`

### 5.1 Router

* [ ] 新增 `app/routers/sql.py`

  * `GET /v1/sql/sse?question=...`
  * 输出 `text/event-stream`
  * SSE 事件：`token` / `ping` / `error` / `done`

### 5.2 Handler 流程（固定顺序）

* [ ] 读取 resources：db_schema + glossary
* [ ] 读取 prompt：text_to_sql
* [ ] build messages
* [ ] 调 DeepSeek 非流式获取 SQL
* [ ] validate_sql
* [ ] 通过：把 SQL 分片（按行或按字符）以 token event 推送
* [ ] 失败：发 error event + done

**验收**

* [ ] curl 可看到连续 token 与 done

curl 示例（注意 URL 编码）：

```bash
curl -G -N --data-urlencode "question=统计 2026-01-01 到 2026-01-31 Acme 的 GMV（元）" \
"http://127.0.0.1:8000/v1/sql/sse"
```

---

## 6. 测试用例（只测“合规 + join 关键字”，不执行 SQL）

### 6.1 用例清单（10 条）

* [ ] 新增 `tests/test_text_to_sql_cases.py`
* [ ] 测试问题列表（固定）：

  1. 列出 org_name=Acme 下 active 用户邮箱、注册时间，倒序前10
  2. 统计 2026-01-01 到 2026-01-31 Acme GMV（元）
  3. Alice Zhang 在 2026-01 消费金额（元），不含退款取消
  4. 2026-01 销售额最高商品 Top3：商品名/品类/GMV(元)
  5. 2026-01 各组织活跃用户数（paid），前10
  6. 2026-01 各城市 GMV（元）与活跃用户数，按 GMV 降序
  7. 2026-01 pro 订阅用户 GMV（元）
  8. 2026-01 有 active 订阅但无 paid 订单用户：邮箱/plan/started_at 前50
  9. 2026-01 各品类 GMV（元）前10
  10. “最近活跃用户趋势怎么样？”（应输出 NEED_CLARIFY 注释 + 空结果 SQL）

### 6.2 断言规则

每条 SQL 都要断言：

* [ ] 通过 `validate_sql`
* [ ] 不含 DML/DDL
* [ ] 不含 `SELECT *`
* [ ] 包含 `LIMIT`（第10条也要 LIMIT 0）
* [ ] GMV/活跃用户类必须出现 `order_status='paid'`（或等价条件）
* [ ] join 类用例至少包含合理表名组合（关键字包含即可）：

  * 如 GMV：应出现 `orders`，且组织相关应 join `users` + `orgs`
  * Top 商品：应出现 `order_items` + `products` + `categories`

> 测试不需要真实调用 DeepSeek：可以用“录制结果 fixture”，或把 LLM 调用层抽象成接口，测试时 mock 返回 SQL。

---

## 7. 最终验收（必须全部通过）

* [ ] 服务启动：`GET /v1/sql/sse` 可用
* [ ] 任意正常问题：返回**只包含 SQL** 的 SSE token 流 + done
* [ ] 故意越权（让模型输出 UPDATE/ALTER）：被 validator 拦截并 SSE error
* [ ] 模糊问题（最近趋势）：SQL 顶部有 `-- NEED_CLARIFY:` 且查询为空结果（`WHERE 1=0 LIMIT 0`）
* [ ] tests 全绿

---

## 8. Codex 输出要求（交付物）

* [ ] 列出新增/修改文件清单
* [ ] 给出运行命令
* [ ] 给出 2 条 curl 示例（一个正常、一个 NEED_CLARIFY）
* [ ] 如有配置新增（resources/prompts 路径），更新 README.md

---

如果你把你项目当前目录结构（`app/` 下有哪些模块、DeepSeek client 放哪）贴一下，我还能把上面任务列表里的**文件路径与函数名**替换成完全贴合你仓库的版本，让 Codex 基本“照抄就能干”。
