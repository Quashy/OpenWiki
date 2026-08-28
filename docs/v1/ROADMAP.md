# OpenWiki V2 v1 开发路线图

> 版本：v2.0
> 日期：2026-08-28
> 状态：开发基线
> 来源：[PRD](../PRD-LLM-Wiki知识库系统.md)、[TRD](../TRD-LLM-Wiki知识库系统.md)、[Architecture](../architecture.md)、[API](../api/API.md)
> 变更：v2.0 — 调整为 demo 优先：M2-M4 构成 demo 主线（M4 退出即可演示）；观测（Langfuse）随里程碑逐层接入而非集中交付；图谱交互视图前移至 M3；原治理/门禁里程碑压缩为 M5 工程补齐；显式记录 demo 阶段工程简化清单与 PRD 功能后置清单；新增 PRD 功能追踪矩阵

---

## 1. 定位

本文只回答三个问题：

1. 按什么里程碑推进 v1，demo 到哪一步。
2. 每个里程碑交付哪些 PRD 功能与接口，用什么条件验收。
3. 哪些 PRD/TRD 内容在 demo 阶段被简化或后置，后续在哪里补齐。

PRD 定义产品能力，TRD 定义技术实现，`docs/api/openapi.yaml` 定义接口主契约。本文件不重复 PRD/TRD 的完整细节，只记录开发顺序、功能与接口批次、阶段门禁。按 AGENTS.md 的优先级约定，本文件与 TRD 的简化冲突以本文件为准，补齐位置在表中注明。

## 2. v1 开发口径

v1 先完成一个可演示、可内部试用的闭环：

```text
注册/加入团队
  -> 配置模型
  -> 创建 Source KB / Wiki KB
  -> 上传文档并分块向量化
  -> 六阶段 Wiki ingest
  -> 浏览 Wiki / 图谱
  -> 单 KB RAG 问答
  -> 编辑、版本、审计与观测（demo 后）
```

**Demo 定义**：M0-M4 为 demo 主线，**M4 退出门禁通过即可对外演示**（上传 → 生成 → 浏览/图谱 → 问答带引用的完整链路）。M5 为 demo 后的工程补齐，M6 为演进。

通用收敛口径：

- API 前缀为 `/api/v1`，接口以 `docs/api/openapi.yaml` 为准。
- Workspace 先按"当前团队"实现，不开放多团队创建、列表和切换接口。
- 问答会话绑定单个 `kb_id`，不实现多 KB 联合问答。
- Source KB 与 Wiki KB 保持独立；Wiki KB 可绑定多个 Source KB。
- Wiki ingest 固定为 Extract、Citation、Taxonomy、Summary、Reduce、Post-process 六阶段流水线。
- 检索采用 Dense、Sparse、GraphRAG 三路召回 + RRF 融合。
- 长任务状态统一落到 `task_pending_ops`，外部只依赖 `GET /tasks/{task_id}`。
- 写操作必须接入 RBAC、审计日志、统一错误结构和自动化测试。

### 2.1 Demo 阶段工程简化清单

以下 TRD 工程项在 demo 阶段（M2-M4）简化实现，M5 补齐。这是有意的收敛，不是遗漏：

| TRD 工程项 | demo 阶段处理 | 补齐位置 |
|---|---|---|
| Redis 分布式锁 `wiki:ingest:{kb_id}` + per-slug 锁 | 不实现；单 worker 串行执行 + `task_pending_ops` 状态检查保证"同一 Wiki KB 同时只有一个 ingest" | M5 |
| 任务崩溃恢复（claim 超时 90 分钟视为 stale 可回收） | 不做；失败任务走手动重试 | M5 |
| LLM 429 限流固定 60 秒 backoff + ARQ 指数退避 | 普通重试即可 | M5 |
| 性能指标（PRD 5.1 全表） | 不验证 | M5 单用户自查 / M6 并发 |
| 审计日志查询界面 | 只写不查（M1 已交付写入基础设施，随写接口顺带保留） | M5 |
| 20 人并发问答 | 不做 | M6 |

### 2.2 PRD 功能后置清单

以下 PRD 功能明确后置到 M6，由真实需求触发，不在 v1 demo 主线上：

| PRD 功能 | PRD 章节 | v1 处理 |
|---|---|---|
| 多团队创建/切换 | 4.1.2 | 收敛为单"当前团队" |
| 多 KB 联合问答 | 4.6.1 | 会话绑定单个 `kb_id`，契约不支持多选 |
| auto_ingest 自动触发 + 30 秒 debounce | 4.5.1 / 4.5.4 | 契约字段 `wiki_config.auto_ingest` 保留但 v1 恒为手动触发 |
| KB 启用/停用完整语义 | 4.2.1 | `status` 字段已随 M1 交付，"停用后不参与检索"未生效 |
| 会话标题自动生成 | 4.6.5 | v1 使用用户输入或默认标题 |
| 新会话推荐问题 | 4.6.6 | 不做 |
| 删除文档后来源页标记"来源已删除" | 4.3.4 | 删除仅清理 chunk/向量/索引与审计记录，不动 Wiki 页面 |
| OpenAI Embedding 与多维向量 | 4.8.2 | v1 仅 Ollama 1024 维 embedding |

### 2.3 观测 Dashboard 方向

Langfuse 在 v1 中优先用于 LLM/RAG 业务链路追踪和质量分析，不替代 Prometheus/Grafana 类系统监控。M2-M4 按链路逐步补齐 trace/span，M5 统一验收以下 dashboard 方向：

- 文档摄入健康度：上传数、处理成功率、失败率、embedding 耗时、chunk 数、失败原因。
- RAG 问答质量：query、召回 chunk、引用命中率、回答评分、无答案率。
- 成本与性能：模型调用次数、token、耗时 P50/P95，并按模型、KB 维度拆分。

## 3. 里程碑总览

状态只使用：`未开始`、`进行中`、`阻塞`、`已完成`。

| 里程碑 | 用户能力 | demo 定位 | 状态 | 主要完成证据 |
|---|---|---|---|---|
| M0 | 工程与契约基线可启动、可迁移、可校验 | — | 已完成 | 2026-08-27：迁移、OpenAPI lint、前后端基础检查通过 |
| M1 | 注册登录、管理成员与模型配置、创建/绑定 KB | — | 已完成 | 2026-08-27：RBAC、模型探测、KB 骨架和前端 M1 外壳测试通过 |
| M2 | 上传文档、打标签、查看分块与处理状态 | demo 第一步 | 已完成 | 2026-08-28：上传、分块、向量化、检索基线、文档处理 trace 通过 |
| M3 | 触发 Wiki 生成，浏览页面与知识图谱 | demo 第二步 | 已完成 | 2026-08-28：六阶段 ingest、页面浏览、图谱交互、真实 DeepSeek trace 和自动化检查通过 |
| M4 | 单 KB 问答，流式回答带引用可溯源 | 🎯 demo 达成 | 未开始 | SSE、三路检索、引用跳转、问答 trace、演示走查通过 |
| M5 | 编辑 Wiki、版本回滚、审计查询、观测闭环 | demo 后工程补齐 | 未开始 | 编辑、版本、审计、Langfuse 闭环、全量回归通过 |
| M6 | — | 演进 | 未开始 | 由试用数据或明确需求触发 |

## 4. 里程碑明细

### M0：工程与契约基线（已完成）

**目标**

建立后续开发共享的工程骨架、数据库迁移、质量命令和接口契约校验。

**PRD 功能清单**

不交付 PRD 业务功能；为 PRD 5.2（安全基础设施：统一错误结构、请求 ID、配置校验）和 5.3（部署：Docker Compose 服务编排）打底，并固定质量语料（重复文档、别名、冲突事实、跨文档关系、精确编号、无答案问题）供 M2-M4 验收复用。

**交付**

- FastAPI、React/Vite/TypeScript、SQLAlchemy、Alembic 基础工程。
- PostgreSQL 16、pgvector、pg_bigm、Redis、Langfuse、Ollama 连接配置。
- `.env.example`、配置校验、结构化日志、统一错误响应、请求 ID。
- OpenAPI 契约检查、API 契约测试入口、后端测试目录。
- 固定质量语料：重复文档、别名、冲突事实、跨文档关系、精确编号、无答案问题。

**接口**

M0 不交付业务接口；只建立接口契约和后端测试入口。

**退出门禁**

- 空库可执行 Alembic 迁移，`vector` 和 `pg_bigm` 扩展可用。
- 前后端、数据库和依赖服务可按文档启动。
- OpenAPI 契约检查通过。
- 后端最小测试通过，前端生产构建按需通过。

**完成证据（2026-08-27）**

- 后端：`python -m pytest` 通过。
- 前端：`npm --prefix "frontend" run build` 通过。
- API 契约：`npm run api:lint` 通过。
- Docker：`docker compose config` 通过；PostgreSQL 镜像可构建并从源码安装 `pg_bigm`。
- Alembic：空库执行 `python -m alembic upgrade head` 通过，扩展版本为 `pg_bigm 1.2`、`vector 0.8.6`。

### M1：账号、团队、模型配置、KB 骨架（已完成）

**目标**

完成真实身份、当前团队边界、RBAC、模型配置和知识库基础管理。

**PRD 功能清单**

- 4.1.1 注册与登录：账号密码；首个注册用户创建当前团队并成为 Admin。
- 4.1.2 团队管理：成员邀请/移除/角色分配、团队重命名（多团队创建/切换后置，见 2.2）。
- 4.1.3 审计日志：写操作记录（查询界面在 M5 交付）。
- 4.2.1 创建 Source KB：名称、描述、分块参数、Embedding 模型选定不可改（启用/停用完整语义后置）。
- 4.2.2 知识库列表：分区展示与基础查询（文档数、状态补全在 M2）。
- 4.5.1 创建 Wiki KB：创建 + 绑定 Source KB（`wiki_config` 生效在 M3）。
- 4.8.1 LLM 模型配置：OpenAI/DeepSeek Key 加密入库、连通性测试。
- 4.8.2 Embedding 配置：Ollama 服务地址、模型发现与实测维度探测（OpenAI Embedding 后置）。
- 5.2 安全基础：bcrypt、JWT、RBAC、API Key 掩码。

**接口**

- Auth：`POST /auth/register`、`POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout`
- Workspace：`GET /workspaces/current`、`PATCH /workspaces/current`
- Members：`GET /workspaces/current/members`、`POST /workspaces/current/members`、`PATCH /workspaces/current/members/{user_id}`、`DELETE /workspaces/current/members/{user_id}`
- Model Settings：`GET /admin/llm-config`、`PUT /admin/llm-config`、`POST /admin/llm-config/test`、`GET /admin/ollama-config`、`PUT /admin/ollama-config`、`GET /admin/ollama/models`、`POST /admin/ollama/models/probe`
- Knowledge Bases：`GET /kbs`、`POST /kbs`、`GET /kbs/{kb_id}`、`PATCH /kbs/{kb_id}`、`DELETE /kbs/{kb_id}`、`POST /kbs/{kb_id}/bindings`、`DELETE /kbs/{kb_id}/bindings/{source_kb_id}`

**退出门禁**

- 首个注册用户创建当前团队并成为 Admin。
- 后续用户需由 Admin 加入团队后才能访问团队资源。
- Admin、Editor、Viewer 权限矩阵覆盖允许和拒绝用例。
- 禁止移除或降级最后一名 Admin。
- LLM API Key 加密入库，接口只返回掩码。
- Ollama 模型发现返回 tag、digest、capability、实测维度和 v1 可用性。
- KB 创建后 Embedding 身份字段不可被普通更新接口修改。

**完成证据（2026-08-27）**

- 后端：`python -m pytest "backend/tests"` 通过。
- 前端：`npm --prefix "frontend" run build` 通过。
- Alembic：`python -m alembic upgrade head --sql` 通过，M1 表结构可生成 PostgreSQL SQL。
- 在线迁移未在宿主机验证：当前 `DATABASE_URL` 指向 Docker 网络主机名 `db`，宿主机直接运行无法解析。

### M2：Source KB 文档摄入闭环

**目标**

完成从文件上传到可检索 chunk 的端到端闭环，并接入第一批观测。

**PRD 功能清单**

- 4.2.2 知识库列表补全：文档数、状态、关键词搜索与标签筛选。
- 4.2.3 文档标签：多标签标记、按标签筛选、标签增删改。
- 4.3.1 支持格式：仅 `.md` 与 `.txt`。
- 4.3.2 文件上传：SHA-256 哈希去重（KB 内）、批量上传、异步处理状态流转、失败重试、上传时选标签。
- 4.3.3 文档列表与详情：文件名/标签/分块数/状态列表，原文预览，chunk 列表（内容、header_path、序号），元信息。
- 4.3.4 文档删除：级联删除 chunk、向量与全文索引，记审计（来源页标记后置，见 2.2）。
- 4.4.1 Header 路径感知切块（Markdown）：H1-H3 标题边界切节，chunk 携带 header_path。
- 4.4.2 超长章节二次切分：段落/句子递归切分，共享 header_path，80 字符 overlap，标题边界不重叠。
- 4.4.3 纯文本切分（TXT）：递归字符切分，header_path 为空。
- 4.4.4 Chunk 数据结构：content、header_path、seq、start_pos/end_pos、document_id、kb_id。
- 4.4.5 向量化上下文拼接：`" > ".join(header_path) + "\n" + content`，BM25 索引同样拼入 header_path。
- 4.4.6 分块预览：粘贴文本预览切分结果，展示 header_path、字符数、内容。
- 4.7 观测第一批：Langfuse `document_process` trace，含 chunking、embedding span（对应 PRD 4.7「文档解析进度」维度）。

**接口**

- Documents：`POST /kbs/{kb_id}/documents/upload`、`GET /kbs/{kb_id}/documents`、`GET /documents/{document_id}`、`DELETE /documents/{document_id}`、`POST /documents/{document_id}/retry`
- Tags：`GET /kbs/{kb_id}/tags`、`POST /kbs/{kb_id}/tags`、`PATCH /kbs/{kb_id}/tags/{tag_id}`、`DELETE /kbs/{kb_id}/tags/{tag_id}`
- Chunk Preview：`POST /kbs/{kb_id}/chunk-preview`
- Tasks：`GET /tasks/{task_id}`

**退出门禁**

- 只接受 `.md` 和 `.txt`，文件大小、扩展名、文件名安全校验有效。
- 同一 KB 内相同 SHA-256 文件返回 `409`，不同 KB 可独立上传。
- Markdown Header-aware 分块、TXT 递归分块、overlap、`header_path`、字符位置符合固定语料预期。
- 文档处理任务可查询进度、失败原因和重试结果。
- Dense 与 Sparse 在固定问题 Top-K 中能召回预期证据。
- 删除文档后，其 chunk、embedding 和全文索引不可再被召回。
- 文档处理可在 Langfuse 中查到 `document_process` trace（含分块与向量化 span）。

**完成证据（2026-08-28）**

- 后端：`$env:PYTHONPATH="backend"; python -m pytest backend/tests` 通过，18 passed。
- 前端：`npm --prefix "frontend" run build` 通过，存在 Vite chunk size warning，不阻塞 M2。
- API 契约：`npm run api:lint` 通过。
- Alembic：运行中数据库版本为 `0006_doc_uploader_username (head)`，包含 M2 文档摄入迁移。
- 运行环境：frontend、backend、worker、db、redis、Langfuse 容器均正常运行。
- 观测：最新真实 `document_process` trace 可在 Langfuse 中看到 `chunking`、`embedding`、`indexing` span；`embedding` span 记录 `chunk_count`、`model`、`embedding_dim`。

**剩余风险**

- 非 `.md/.txt`、超大小、不同 KB 重复上传、非失败文档重试 `409` 已由实现覆盖，后续若需要更硬的里程碑验收，可补充逐项 API 集成断言。

### M3：Wiki 生成、浏览与知识图谱

**目标**

完成 Wiki KB 的六阶段生成、页面存储、页面浏览、图谱数据与交互视图，并接入第二批观测。

**PRD 功能清单**

- 4.5.1 `wiki_config` 生效：LLM 模型、超时、重试、温度（auto_ingest 自动触发后置，见 2.2）。
- 4.5.2 Wiki 页面类型：index/source/entity/concept/overview/analysis 六类页面。
- 4.5.3 页面内容结构：数据库元信息字段（slug、page_type、summary、category_path、aliases、source_refs）+ Markdown 正文（`SUMMARY:` 首行、`[[slug|显示名]]` 双链）。
- 4.5.4 Wiki 生成（Ingest）：手动触发、同 KB 单任务互斥、以文档为粒度追踪状态、失败文档单独重试、全量重建（二次确认、重建中不可查询）。
- 4.5.5 六阶段流水线：Extract、Citation、Taxonomy、Summary、Reduce、Post-process，per-slug 单事务写入，实体关系随 Reduce 写入。
- 4.5.6 Wiki 页面浏览：左侧 category_path 目录树、Markdown 渲染、双链跳转、页面头部类型/来源数/更新时间、全文搜索（复用 chunk 检索）、来源文档跳转原文。
- 4.5.9 知识图谱：entities/relations 关系表存储、图谱数据接口、ECharts 交互视图（缩放、拖拽、节点跳转到 Wiki 页面、实体类型/关系类型筛选、节点大小按类型区分）。
- 5.4 可用性：ingest 按文档粒度部分成功，已成功页面保留可用。
- 4.7 观测第二批：Langfuse `wiki_ingest` trace，六阶段各 span、每阶段 LLM 输入/输出、耗时与 token（对应 PRD 4.7「Wiki 流水线」维度）。

**接口**

- Wiki Tasks：`POST /wiki/{kb_id}/ingest`、`POST /wiki/{kb_id}/rebuild`
- Wiki Pages：`GET /wiki/{kb_id}/pages`、`GET /wiki-pages/{page_id}`
- Wiki Graph：`GET /wiki/{kb_id}/graph`

**退出门禁**

- 六阶段流水线完整执行，并记录阶段状态、错误和 Langfuse trace。
- 生成 `index/source/entity/concept/overview/analysis` 六类页面。
- 页面正文遵循 `SUMMARY:`、Markdown、`[[slug|显示名]]` 双链约定。
- `source_refs` 和 Citation chunk ID 指向真实记录。
- Post-process 后不存在死链和内部标记残留。
- 重复 ingest 不产生重复页面、重复实体或重复关系。
- 全量重建期间 Wiki KB 不可查询，完成后恢复可用。
- 图谱视图支持缩放、拖拽、节点跳转、实体类型和关系类型筛选。
- Wiki ingest 可在 Langfuse 中按 trace 查看六阶段各 span 的 LLM 输入输出。

**推进记录（2026-08-28）**

- 后端：新增 Wiki 页面、修订、实体、关系模型和迁移；实现 `POST /wiki/{kb_id}/ingest`、`POST /wiki/{kb_id}/rebuild`、`GET /wiki/{kb_id}/pages`、`GET /wiki-pages/{page_id}`、`GET /wiki/{kb_id}/graph`。
- 流水线：接入六阶段任务状态、页面 upsert、来源页、实体/概念页、overview、analysis、index、Wiki page chunk 重新向量化、实体关系 upsert、审计日志和 Langfuse `wiki_ingest` trace；真实运行优先使用 `.env` 中 `DEEPSEEK_API_KEY`。
- 前端：Wiki 浏览器支持目录树、搜索、类型筛选、任务进度和双链跳转；知识图谱支持 ECharts 缩放/拖拽、实体类型/关系类型筛选、节点跳转 Wiki 页面。
- 自动化检查：`python -m pytest "backend/tests"` 通过，20 passed；`npm --prefix "frontend" run build` 通过，存在 Vite chunk size warning；`npm run api:lint` 通过；`python -m alembic upgrade head --sql` 通过。
- 真实环境烟测：使用 DeepSeek Key、Ollama embedding、Docker Compose 后端/worker/db/redis/Langfuse，上传固定语料并触发 Wiki ingest，任务 `fd643a77-f883-4564-b69b-5a3993d799bd` 完成；返回 trace_id `a01ee1b2-781d-4b6f-8f1a-1d6a432f4be5`；生成 11 个页面，覆盖 `index/source/entity/concept/overview/analysis`；图谱 7 个节点、21 条边。
- 页面质量自查：真实生成的 11 个页面死链数 0，内部标记残留页面数 0。

### M4：单 KB RAG 问答（🎯 Demo 达成）

**目标**

完成单个物理 KB 范围内的三路检索、RRF 融合、SSE 流式回答和引用溯源。M4 退出门禁通过即 demo 可演示。

**PRD 功能清单**

- 4.6.1 问答入口：Web 对话界面，左侧会话列表、右侧对话区，提问前选择单个知识库（多选后置，见 2.2）。
- 4.6.2 多路混合检索：Dense（pgvector 余弦）、Sparse（pg_bigm）、GraphRAG（实体名/别名匹配 + 1 跳扩展）三路并行，RRF 融合（k=60），Wiki 页面 chunk 加权 1.2，Top-8 截断。
- 4.6.3 RAG 问答流程：加载历史 → 查询改写（指代消解、意图判断）→ 三路检索 → RRF 融合 → 阈值过滤 + Top-N → 组装 Prompt → SSE 流式生成；前端展示 pipeline 进度。
- 4.6.4 引用溯源：回答角标 `[1]`、`[2]`，底部引用列表（文档名、header_path、片段），点击跳转原文/Wiki 页面，区分原始文档与 Wiki 页面来源。
- 4.6.5 多轮对话：上下文改写为独立查询再检索，最近 10 轮（20 条消息）进入上下文，历史持久化（标题自动生成后置，见 2.2）。
- 4.6.6 会话管理：会话列表、重命名、删除、记录所选知识库范围（推荐问题后置，见 2.2）。
- 4.7 观测第三批：Langfuse `chat_qa` trace（query_understand、三路检索、merge、completion span），SSE done 事件返回 trace_id（对应 PRD 4.7「LLM 调用链路/检索过程」维度）。

**接口**

- Chat Sessions：`POST /chat/sessions`、`GET /chat/sessions`、`PATCH /chat/sessions/{session_id}`、`DELETE /chat/sessions/{session_id}`
- Chat Messages：`GET /chat/sessions/{session_id}/messages`
- Chat Stream：`GET /chat/sessions/{session_id}/stream`

**退出门禁**

- 创建会话只接受单个 `kb_id`；`kb_ids` 或多 KB 参数返回契约错误。
- LOAD_HISTORY、QUERY_UNDERSTAND、CHUNK_SEARCH、MERGE、FILTER、PROMPT、STREAM 管线完整。
- Dense、Sparse、GraphRAG 均参与召回，GraphRAG 无命中时不影响主流程。
- RRF 后 Top-8 证据可复现，回答引用只指向进入上下文的片段。
- SSE 至少包含 `progress`、`token`、`done`、`error` 事件，done 事件携带 trace_id。
- Source KB 和 Wiki KB 均可独立问答，引用可跳转到原文或 Wiki 页面。
- 问答可在 Langfuse 中按 trace_id 定位完整调用链。
- **Demo 演示走查**：用固定语料完成端到端演示（上传 → 生成 → 浏览/图谱 → 问答带引用），走查结果有记录。

### M5：工程补齐（Demo 后）

**目标**

补齐内部试用所需的 Wiki 治理、审计查询、观测闭环和全量验收，兑现 2.1 中 demo 阶段承诺的工程简化项。

**PRD 功能清单**

- 4.5.7 Wiki 页面编辑：浏览器直接编辑 Markdown，保存创建修订快照并重新向量化；人工编辑页面被系统更新时有明确对比入口提示。
- 4.5.8 版本管理：修订历史列表、任意版本查看、任意两版本行级 diff、一键回滚（以新修订实现，不删历史）。
- 4.1.3 审计日志查询：按操作类型和时间筛选的管理界面。
- 4.7 观测收尾闭环：业务记录（问答消息、文档、ingest 任务）可定位到 Langfuse trace；支持按 trace 搜索、按 token/成本排序（trace 三批已在 M2-M4 随做接入，此处统一验收）。
- 5.2 安全验证：密码、JWT、RBAC、API Key 加密、文件上传安全集中检查（实现已在 M1-M4 随做交付，此处只验证）。
- 5.1 单用户性能自查：首 token 延迟、100KB 文档处理、单文档 Wiki ingest、三路检索四项。
- 5.3 部署演练：从空数据库按文档部署，核心路径手工验收有记录。
- 2.1 工程简化项补齐：分布式锁与 per-slug 锁、任务崩溃恢复、429 退避重试。

**接口**

- Wiki Edit：`PUT /wiki-pages/{page_id}`
- Revisions：`GET /wiki-pages/{page_id}/revisions`、`GET /wiki-pages/{page_id}/revisions/{revision_id}`、`GET /wiki-pages/{page_id}/diff`、`POST /wiki-pages/{page_id}/rollback`
- Audit：`GET /admin/audit-logs`

**退出门禁**

- 自动生成、人工编辑、回滚都会创建不可变修订。
- 回滚以新修订实现，不删除历史。
- 人工编辑后被系统更新时，前端有明确对比入口。
- 所有写操作可在审计日志中按类型和时间查询。
- 问答、文档处理、Wiki ingest 可从业务记录定位到 Langfuse trace。
- 后端 pytest 全量通过；前端生产构建通过。
- 固定语料的 Wiki 质量、检索召回、问答引用有验收记录。
- 单用户性能自查四项完成并记录。
- 空库部署演练通过，无数据丢失、错误引用、越权访问、不可恢复任务状态等阻断缺陷。

### M6：v1 后演进

M6 不阻塞 v1 内部试用，由真实需求或试用数据触发，涵盖 2.2 后置清单与工程增强项：

| 方向 | PRD/TRD 引用 | 触发条件 |
|---|---|---|
| 多 Workspace 与团队切换 | PRD 4.1.2 | 出现真实多团队隔离需求 |
| 多 KB 联合问答 | PRD 4.6.1 | 单 KB 问答无法覆盖业务查询范围 |
| OpenAI Embedding 与多维向量 | PRD 4.8.2 | Ollama 质量、成本或部署不满足要求 |
| auto_ingest 自动触发 + debounce | PRD 4.5.1 / 4.5.4 | 手动触发成为高频操作负担 |
| KB 启用/停用完整语义 | PRD 4.2.1 | 需要临时下线某个知识库 |
| 会话标题自动生成 | PRD 4.6.5 | 默认标题影响会话管理体验 |
| 新会话推荐问题 | PRD 4.6.6 | 新用户冷启动困难 |
| 来源页"来源已删除"标记 | PRD 4.3.4 | 来源清理成为 Wiki 治理负担 |
| 长任务并发与分布式锁增强 | TRD 5.3.2 | Wiki ingest 或文档任务出现持续排队 |
| 系统指标观测（队列深度、错误率） | PRD 4.7 | 任务排队或错误率需要主动监控 |
| 完整生产化部署 | PRD 5.3 | 需要交付开发机外的稳定部署环境 |
| 20 人并发优化 | PRD 5.1 | 有明确并发目标、数据规模和压测基线 |

---

## 5. 接口完成定义

一个接口只有同时满足以下条件，才算完成：

- OpenAPI schema、后端实现、前端调用保持一致（契约一致性由 Redocly lint 全局保障）。
- 后端执行认证、Workspace 隔离和 RBAC 校验（由共享依赖统一实现并集中测试）。
- 写接口完成真实数据库写入、审计日志和事务边界。
- 长任务接口返回任务 ID，并能通过 `GET /tasks/{task_id}` 查询稳定状态。
- 前端页面不使用永久 mock 数据。

测试策略：后端只保留两类 pytest 测试——横切关注点冒烟（认证/RBAC/审计各覆盖一次）与固定语料管线测试（分块、召回、Wiki 后处理）；前端不编写测试，以 tsc 构建、页面手动走查验收。

## 6. PRD 功能追踪矩阵

里程碑列标注所属阶段：M0-M1 已完成、M2-M4 demo 主线、M5 工程补齐、M6 演进。"v1 处理"列取值 `v1` 或 `部分`（注明收敛或后置点，详见表 2.1 / 2.2）。

| PRD 章节 | 功能 | v1 处理 | 里程碑 |
|---|---|---|---|
| 4.1.1 | 注册与登录（首用户建团成 Admin） | v1 | M1（已完成） |
| 4.1.2 | 团队管理（成员/角色/重命名） | 部分：多团队创建/切换后置 | M1（已完成） |
| 4.1.3 | 审计日志（写入） | v1 | M1（已完成） |
| 4.1.3 | 审计日志（查询界面、按类型/时间筛选） | v1 | M5 |
| 4.2.1 | 创建 Source KB（分块参数、Embedding 选定不可改） | 部分：启用/停用完整语义后置 | M1（已完成） |
| 4.2.2 | 知识库列表（分区、搜索、筛选） | 部分：骨架 M1，文档数/状态 M2 补全 | M1（已完成）、M2（已完成） |
| 4.2.3 | 文档标签（多标签、筛选、增删改） | v1 | M2（已完成） |
| 4.3.1 | 支持格式（.md / .txt） | v1 | M2（已完成） |
| 4.3.2 | 文件上传（SHA-256 去重、批量、异步状态、重试、选标签） | v1 | M2（已完成） |
| 4.3.3 | 文档列表与详情（预览、chunk 列表、元信息） | v1 | M2（已完成） |
| 4.3.4 | 文档删除（级联清理、审计） | 部分：来源页"来源已删除"标记后置 | M2（已完成） |
| 4.4.1 | Header 路径感知切块（Markdown） | v1 | M2（已完成） |
| 4.4.2 | 超长章节二次切分（overlap） | v1 | M2（已完成） |
| 4.4.3 | 纯文本切分（TXT） | v1 | M2（已完成） |
| 4.4.4 | Chunk 数据结构 | v1 | M2（已完成） |
| 4.4.5 | 向量化上下文拼接（header_path 拼入 embedding 与 BM25） | v1 | M2（已完成） |
| 4.4.6 | 分块预览 | v1 | M2（已完成） |
| 4.5.1 | 创建 Wiki KB（名称、描述、绑定） | v1 | M1（已完成） |
| 4.5.1 | wiki_config（LLM 模型、超时、重试、温度） | 部分：auto_ingest 后置 | M3 |
| 4.5.2 | Wiki 页面类型（六类页面） | v1 | M3 |
| 4.5.3 | 页面内容结构（元信息字段 + SUMMARY 行 + 双链） | v1 | M3 |
| 4.5.4 | Wiki 生成触发（手动、互斥、全量重建） | 部分：自动触发 + debounce 后置 | M3 |
| 4.5.5 | 六阶段流水线（Extract/Citation/Taxonomy/Summary/Reduce/Post-process） | v1 | M3 |
| 4.5.6 | Wiki 页面浏览（目录树、双链、来源跳转、搜索） | v1 | M3 |
| 4.5.7 | Wiki 页面编辑（修订快照、重新向量化、人工编辑提示） | v1 | M5 |
| 4.5.8 | 版本管理（历史、diff、回滚） | v1 | M5 |
| 4.5.9 | 知识图谱（entities/relations 存储、Reduce 构建） | v1 | M3 |
| 4.5.9 | 图谱可视化（ECharts 缩放/拖拽/跳转/筛选） | v1 | M3 |
| 4.6.1 | 问答入口（对话界面、选择知识库） | 部分：单 KB 收敛，多选后置 | M4 |
| 4.6.2 | 多路混合检索（三路并行 + RRF + Wiki boost） | v1 | M4 |
| 4.6.3 | RAG 问答流程（改写、检索、流式、进度） | v1 | M4 |
| 4.6.4 | 引用溯源（角标、来源列表、跳转、类型区分） | v1 | M4 |
| 4.6.5 | 多轮对话（改写、10 轮窗口、持久化） | 部分：标题自动生成后置 | M4 |
| 4.6.6 | 会话管理（列表、重命名、删除、范围记录） | 部分：推荐问题后置 | M4 |
| 4.7 | 观测：文档解析进度 trace | v1 | M2（已完成） |
| 4.7 | 观测：Wiki 流水线六阶段 trace | v1 | M3 |
| 4.7 | 观测：LLM 调用链路 + 检索过程 trace、trace_id 返回 | v1 | M4 |
| 4.7 | 观测：面板访问、trace 搜索、token/成本排序闭环 | v1 | M5 |
| 4.7 | 观测：系统指标（队列深度、错误率） | 部分：后置 | M6 |
| 4.8.1 | LLM 模型配置（OpenAI/DeepSeek、加密、测试） | v1 | M1（已完成） |
| 4.8.2 | Embedding 配置（Ollama 发现/探测） | 部分：OpenAI Embedding 与多维向量后置 | M1（已完成） |
| 5.1 | 性能（首 token、解析、ingest、检索） | 部分：M5 单用户自查，并发后置 | M5、M6 |
| 5.2 | 安全（bcrypt、AES、隔离、上传限制、审计） | v1：随里程碑实现，M5 集中验证 | M1-M2（已完成）、M3-M4、M5 |
| 5.3 | 部署（Docker Compose、持久化卷） | v1：M0 基线，M5 空库部署演练 | M0（已完成）、M5 |
| 5.4 | 可用性（失败隔离、重试、部分成功） | v1 | M2（已完成）、M3 |
| 5.5 | 国际化（界面中文） | v1 | 全程 |

## 7. 维护规则

- 开始里程碑时将状态改为 `进行中`，完成后附测试或验收证据。
- 日常开发按改动范围运行最快相关检查；里程碑退出时执行必要验收，不强制静态检查门禁。
- OpenAPI、Docker、数据库迁移只在相关文件变化时触发专项检查。
- 范围变化必须先更新本文件和 OpenAPI，再改实现。
- PRD/TRD 与本文件冲突时，先确认是否属于 v1 收敛或 demo 简化（见 2.1 / 2.2）；确认后同步修改相关文档。
- 不为后续里程碑保留永久空实现；提前实现的接口也必须满足所属里程碑的完成定义。
