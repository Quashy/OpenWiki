# OpenWiki V2 v1 开发路线图

> 版本：v1.1  
> 日期：2026-08-27  
> 状态：开发基线  
> 来源：[PRD](../PRD-LLM-Wiki知识库系统.md)、[TRD](../TRD-LLM-Wiki知识库系统.md)、[Architecture](../architecture.md)、[API](../api/API.md)

---

## 1. 定位

本文只回答两个问题：

1. 按什么里程碑推进 v1。
2. 每个里程碑要交付哪些接口，并用什么条件验收。

PRD 定义产品能力，TRD 定义技术实现，`docs/api/openapi.yaml` 定义接口主契约。本文件不重复 PRD/TRD 的完整细节，只记录开发顺序、接口批次和阶段门禁。

## 2. v1 开发口径

v1 先完成一个可内部试用的闭环：

```text
注册/加入团队
  -> 配置模型
  -> 创建 Source KB / Wiki KB
  -> 上传文档并分块向量化
  -> 六阶段 Wiki ingest
  -> 浏览 Wiki / 图谱
  -> 单 KB RAG 问答
  -> 编辑、版本、审计与观测
```

本阶段采用以下收敛口径：

- API 前缀为 `/api/v1`，接口以 `docs/api/openapi.yaml` 为准。
- Workspace 先按“当前团队”实现，不开放多团队创建、列表和切换接口。
- 问答会话绑定单个 `kb_id`，不实现多 KB 联合问答。
- Source KB 与 Wiki KB 保持独立；Wiki KB 可绑定多个 Source KB。
- Wiki ingest 固定为 Extract、Citation、Taxonomy、Summary、Reduce、Post-process 六阶段流水线。
- 检索采用 Dense、Sparse、GraphRAG 三路召回 + RRF 融合。
- 长任务状态统一落到 `task_pending_ops`，外部只依赖 `GET /tasks/{task_id}`。
- 写操作必须接入 RBAC、审计日志、统一错误结构和自动化测试。

## 3. 里程碑总览

状态只使用：`未开始`、`进行中`、`阻塞`、`已完成`。

| 里程碑 | 目标 | 状态 | 主要完成证据 |
|---|---|---|---|
| M0 | 工程、数据库与接口契约基线 | 未开始 | 本地启动、迁移、OpenAPI lint、基础测试通过 |
| M1 | 账号、团队、模型配置、KB 骨架 | 未开始 | 权限矩阵和模型探测测试通过 |
| M2 | Source KB 文档摄入闭环 | 未开始 | 上传、分块、向量化、检索基线通过 |
| M3 | Wiki 生成与浏览 | 未开始 | 六阶段 ingest、页面、图谱数据通过 |
| M4 | 单 KB RAG 问答 | 未开始 | SSE、三路检索、引用跳转通过 |
| M5 | Wiki 治理、审计与观测补齐 | 未开始 | 编辑、版本、回滚、审计、Langfuse 闭环通过 |
| M6 | 内部试用门禁 | 未开始 | 全量回归、性能、安全和 PRD 追踪通过 |
| M7 | v1 后演进 | 未开始 | 由试用数据或明确需求触发 |

---

## 4. 里程碑明细

### M0：工程与契约基线

**目标**

建立后续开发共享的工程骨架、数据库迁移、质量命令和接口契约校验。

**交付**

- FastAPI、React/Vite/TypeScript、SQLAlchemy、Alembic 基础工程。
- PostgreSQL 16、pgvector、pg_bigm、Redis、Langfuse、Ollama 连接配置。
- `.env.example`、配置校验、结构化日志、统一错误响应、请求 ID。
- OpenAPI lint、API 契约测试入口、后端集成测试目录、前端测试入口。
- 固定质量语料：重复文档、别名、冲突事实、跨文档关系、精确编号、无答案问题。

**接口**

M0 不交付业务接口；只建立接口契约和测试入口。

**退出门禁**

- 空库可执行 Alembic 迁移，`vector` 和 `pg_bigm` 扩展可用。
- 前后端、数据库和依赖服务可按文档启动。
- OpenAPI lint 通过。
- 基础 lint、类型检查和最小测试通过。

### M1：账号、团队、模型配置、KB 骨架

**目标**

完成真实身份、当前团队边界、RBAC、模型配置和知识库基础管理。

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

### M2：Source KB 文档摄入闭环

**目标**

完成从文件上传到可检索 chunk 的端到端闭环。

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

### M3：Wiki 生成与浏览

**目标**

完成 Wiki KB 的六阶段生成、页面存储、页面浏览和图谱事实源。

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

### M4：单 KB RAG 问答

**目标**

完成单个物理 KB 范围内的三路检索、RRF 融合、SSE 流式回答和引用溯源。

**接口**

- Chat Sessions：`POST /chat/sessions`、`GET /chat/sessions`、`PATCH /chat/sessions/{session_id}`、`DELETE /chat/sessions/{session_id}`
- Chat Messages：`GET /chat/sessions/{session_id}/messages`
- Chat Stream：`GET /chat/sessions/{session_id}/stream`

**退出门禁**

- 创建会话只接受单个 `kb_id`；`kb_ids` 或多 KB 参数返回契约错误。
- LOAD_HISTORY、QUERY_UNDERSTAND、CHUNK_SEARCH、MERGE、FILTER、PROMPT、STREAM 管线完整。
- Dense、Sparse、GraphRAG 均参与召回，GraphRAG 无命中时不影响主流程。
- RRF 后 Top-8 证据可复现，回答引用只指向进入上下文的片段。
- SSE 至少包含 `progress`、`token`、`done`、`error` 事件。
- Source KB 和 Wiki KB 均可独立问答，引用可跳转到原文或 Wiki 页面。

### M5：Wiki 治理、审计与观测补齐

**目标**

补齐 v1 内部试用所需的人工维护、版本治理、图谱交互、审计和观测闭环。

**接口**

- Wiki Edit：`PUT /wiki-pages/{page_id}`
- Revisions：`GET /wiki-pages/{page_id}/revisions`、`GET /wiki-pages/{page_id}/revisions/{revision_id}`、`GET /wiki-pages/{page_id}/diff`、`POST /wiki-pages/{page_id}/rollback`
- Audit：`GET /admin/audit-logs`
- Graph：补齐 `GET /wiki/{kb_id}/graph` 对前端 ECharts 图谱视图的交互验收。

**退出门禁**

- 自动生成、人工编辑、回滚都会创建不可变修订。
- 回滚以新修订实现，不删除历史。
- 人工编辑后被系统更新时，前端有明确对比入口。
- 图谱视图支持缩放、拖拽、节点跳转、实体类型和关系类型筛选。
- 所有写操作可在审计日志中按类型和时间查询。
- 问答、文档处理、Wiki ingest 可从业务记录定位到 Langfuse trace。

### M6：内部试用门禁

**目标**

证明 v1 在固定环境中功能完整、权限可靠、引用可信、问题可诊断。

**接口**

M6 不新增接口，只做全量验收。

**退出门禁**

- M0 到 M5 全部完成。
- 单元、集成、API 契约、核心 E2E 全部通过。
- 固定语料的 Wiki 质量、检索召回、问答引用有验收记录。
- 密码、JWT、RBAC、API Key 加密、文件上传安全检查通过。
- 单用户性能基准完成：首 token、100KB 文档处理、单文档 Wiki ingest、三路检索。
- 从空数据库按文档可完成核心 E2E。
- 无数据丢失、错误引用、越权访问、不可恢复任务状态等阻断缺陷。

### M7：v1 后演进

M7 不阻塞 v1 内部试用，由真实需求或试用数据触发：

| 方向 | 触发条件 |
|---|---|
| 多 Workspace 与团队切换 | 出现真实多团队隔离需求 |
| 多 KB 联合问答 | 单 KB 问答无法覆盖业务查询范围 |
| OpenAI Embedding 与多维向量 | Ollama 质量、成本或部署不满足要求 |
| 长任务并发与分布式锁增强 | Wiki ingest 或文档任务出现持续排队 |
| 完整生产化部署 | 需要交付开发机外的稳定部署环境 |
| 20 人并发优化 | 有明确并发目标、数据规模和压测基线 |

---

## 5. 接口完成定义

一个接口只有同时满足以下条件，才算完成：

- OpenAPI schema、后端实现、前端调用保持一致。
- 请求参数、响应结构、错误码和分页约定通过契约测试。
- 后端执行认证、Workspace 隔离和 RBAC 校验。
- 写接口完成真实数据库写入、审计日志和事务边界。
- 长任务接口返回任务 ID，并能通过 `GET /tasks/{task_id}` 查询稳定状态。
- 依赖 LLM 或 Embedding 的接口有可复现 stub 测试；关键路径有真实模型回归样本。
- 前端页面不使用永久 mock 数据。

## 6. PRD 模块映射

| PRD 模块 | 里程碑 |
|---|---|
| 认证、团队、角色权限、模型配置 | M1 |
| Source KB、标签、文档上传、文档详情、分块 | M1、M2 |
| Wiki KB、绑定关系、六阶段 ingest、Wiki 浏览 | M1、M3 |
| Wiki 编辑、版本、diff、回滚 | M5 |
| 知识图谱数据与交互视图 | M3、M5 |
| 智能问答、三路检索、SSE、引用、多轮会话 | M4 |
| 审计日志、可观测性、安全与性能 | M0、M5、M6 |

## 7. 维护规则

- 开始里程碑时将状态改为 `进行中`，完成后附测试或验收证据。
- 范围变化必须先更新本文件和 OpenAPI，再改实现。
- PRD/TRD 与本文件冲突时，先确认是否属于 v1 收敛；确认后同步修改相关文档。
- 不为后续里程碑保留永久空实现；提前实现的接口也必须满足所属里程碑的完成定义。
