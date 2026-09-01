# 知衍 KnowWeave v1 API 说明

> 主契约：[`openapi.yaml`](./openapi.yaml)  
> 版本：v1.0  
> 来源：ROADMAP、PRD、TRD、Architecture、`docs/prototype/index.html`

## 1. 契约原则

`openapi.yaml` 是唯一主契约，后端实现、前端 API 类型和契约测试都以它为准。本文只解释约定和关键负例，不覆盖主契约。

文档优先级固定为：

1. `docs/v1/ROADMAP.md`
2. `docs/PRD-LLM-Wiki知识库系统.md`
3. `docs/TRD-LLM-Wiki知识库系统.md`
4. `docs/architecture.md`
5. `docs/prototype/index.html`

原型图只作为信息架构参考：知识库卡片、Source 文档列表/详情、Wiki 目录树、图谱、问答、成员、模型设置、审计日志这些视图映射到 API 分组。原型里的“全部知识库”问答选择与 ROADMAP 冲突，正式 v1 接口不保留。

## 2. 全局约定

- API 前缀：`/api/v1`。
- 认证方式：`Authorization: Bearer <access_token>`。
- 未特别说明的接口都要求认证；`/auth/register`、`/auth/login`、`/auth/refresh` 例外。
- ID 使用 UUID 字符串。
- 时间使用 ISO 8601 `date-time`。
- 列表分页参数统一为 `page`、`page_size`。
- 分页响应统一包含 `items`、`total`、`page`、`page_size`。
- 错误响应统一为：

```json
{
  "error": {
    "code": "validation_error",
    "message": "请求参数不合法",
    "details": {},
    "request_id": "req_..."
  }
}
```

## 3. ROADMAP 覆盖 TRD 的 v1 差异

- Workspace：只允许唯一 Workspace，不提供创建第二 Workspace、Workspace 列表、团队切换接口。
- 成员：后续注册用户默认不属于团队，由 Admin 通过用户名添加成员。
- 会话与问答：只接受单个物理 KB，使用 `kb_id`，不定义 `kb_ids`。
- Wiki KB 问答：选择 Wiki KB 时只检索该 Wiki KB 的页面 chunk，不自动联合检索绑定的 Source KB。
- Embedding：v1 仅支持 Ollama，且仅允许实测维度为 1024 的 embedding 模型创建 KB。
- LLM：全系统同一时刻只有一个活动 LLM 配置，Wiki 生成、查询改写和问答共用。
- 长任务：接口只暴露 `task_pending_ops` 语义和 `GET /tasks/{task_id}`，不暴露 Redis、ARQ、Worker API。

## 4. 权限

角色来自 PRD 权限矩阵：

| 能力 | Admin | Editor | Viewer |
|---|:---:|:---:|:---:|
| 成员管理 | 是 | 否 | 否 |
| 知识库创建、删除、设置 | 是 | 否 | 否 |
| 文档上传、删除、重试 | 是 | 是 | 否 |
| Wiki ingest、重建、编辑、回滚 | 是 | 是 | 否 |
| 浏览知识库、文档、Wiki、图谱 | 是 | 是 | 是 |
| 问答和会话管理 | 是 | 是 | 是 |
| 模型配置、审计日志 | 是 | 否 | 否 |

后端必须执行 RBAC，前端隐藏入口不能作为权限边界。

## 5. 接口分组

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

首个注册用户创建唯一 Workspace 并成为 Admin。后续注册用户可以登录，但没有团队成员身份前不能访问团队资源。

### Current Workspace 与 Members

- `GET /workspaces/current`
- `PATCH /workspaces/current`
- `GET /workspaces/current/members`
- `POST /workspaces/current/members`
- `PATCH /workspaces/current/members/{user_id}`
- `DELETE /workspaces/current/members/{user_id}`

必须始终保留至少一名 Admin。删除最后 Admin 或把最后 Admin 降级返回 `409`。

### Model Settings

- `GET /admin/llm-config`
- `PUT /admin/llm-config`
- `POST /admin/llm-config/test`
- `GET /admin/ollama-config`
- `PUT /admin/ollama-config`
- `GET /admin/ollama/models`
- `POST /admin/ollama/models/probe`

LLM API Key 加密存储，接口只返回掩码和是否已配置。Ollama 模型发现必须返回 tag、digest、capability、实测维度、v1 可用性和不可用原因。

### Knowledge Bases

- `GET /kbs`
- `POST /kbs`
- `GET /kbs/{kb_id}`
- `PATCH /kbs/{kb_id}`
- `DELETE /kbs/{kb_id}`
- `POST /kbs/{kb_id}/bindings`
- `DELETE /kbs/{kb_id}/bindings/{source_kb_id}`
- `POST /kbs/{kb_id}/chunk-preview`

Source KB 和 Wiki KB 使用同一 KB 资源模型，通过 `type=document/wiki` 区分。创建时固化 `embedding_provider=ollama`、`embedding_model_tag`、`embedding_model_digest`、`embedding_dim=1024`，后续更新接口不得修改这些字段。

### Documents 与 Tags

- `POST /kbs/{kb_id}/documents/upload`
- `GET /kbs/{kb_id}/documents`
- `GET /documents/{document_id}`
- `DELETE /documents/{document_id}`
- `POST /documents/{document_id}/retry`
- `GET /kbs/{kb_id}/tags`
- `POST /kbs/{kb_id}/tags`
- `PATCH /kbs/{kb_id}/tags/{tag_id}`
- `DELETE /kbs/{kb_id}/tags/{tag_id}`

上传只接受 `.md` 和 `.txt`，单文件大小受配置限制。同一 KB 内按 SHA-256 去重，重复返回 `409`。删除文档必须同步清理文档 chunk 和向量索引；已摄入 Wiki 的来源页标记来源删除，不自动删除综合页面。

### Tasks

- `GET /tasks/{task_id}`

任务状态事实源是 `task_pending_ops`，状态枚举为 `pending/running/completed/failed`。`stage` 独立表达当前阶段，文档处理包含 `chunking/embedding/indexing`，Wiki ingest 包含 `extracting/citing/taxonomy/summarizing/reducing/postprocessing`。

### Wiki

- `POST /wiki/{kb_id}/ingest`
- `POST /wiki/{kb_id}/rebuild`
- `GET /wiki/{kb_id}/pages`
- `GET /wiki/{kb_id}/graph`
- `GET /wiki-pages/{page_id}`
- `GET /wiki-pages/{page_id}/sources`
- `PUT /wiki-pages/{page_id}`
- `GET /wiki-pages/{page_id}/revisions`
- `GET /wiki-pages/{page_id}/revisions/{revision_id}`
- `GET /wiki-pages/{page_id}/diff`
- `POST /wiki-pages/{page_id}/rollback`

Wiki ingest 使用 Extract、Citation、Taxonomy、Summary、Reduce、Post-process 六阶段流水线。页面类型包括 `index/source/entity/concept/overview/analysis`。每次自动写入、人工编辑和回滚都必须创建不可变修订快照。

### Chat

- `POST /chat/sessions`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}/messages`
- `GET /chat/sessions/{session_id}/stream`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`

会话创建时绑定单个 `kb_id`。流式问答使用会话的 `kb_id`，不允许通过消息请求临时切换 KB。

SSE 事件类型：

```text
event: progress
data: {"stage":"search","message":"正在检索知识库..."}

event: token
data: {"content":"根据"}

event: done
data: {"message_id":"uuid","citations":[],"trace_id":"trace-id"}

event: error
data: {"code":"llm_timeout","message":"LLM 响应超时"}
```

### Audit

- `GET /admin/audit-logs`

审计日志不可删除。所有写操作都要记录，包括成员变更、知识库变更、模型配置、文档上传/删除/重试、Wiki ingest、编辑、回滚和重建。

## 6. 关键负例

| 场景 | 期望 |
|---|---|
| 创建会话时提交 `kb_ids` 数组 | `422 validation_error` |
| 问答流请求临时传入另一个 KB | `422 validation_error` 或忽略该参数并记录契约测试，推荐返回 422 |
| Viewer 调用任意写接口 | `403 forbidden` |
| 非成员访问团队资源 | `403 forbidden` |
| 删除最后一名 Admin | `409 last_admin_required` |
| 降级最后一名 Admin | `409 last_admin_required` |
| 同一 KB 重复上传相同 SHA-256 文件 | `409 document_duplicate` |
| 使用非 embedding 模型创建 KB | `422 embedding_model_invalid` |
| 使用非 1024 维 embedding 模型创建 KB | `422 embedding_dimension_incompatible` |
| KB 的 Ollama tag digest 漂移后检索或写入向量 | `409 embedding_incompatible` |
| Wiki 正在重建时查询 Wiki 或问答 | `409 kb_unavailable` |

## 7. 校验要求

生成或修改接口文档后必须执行：

```powershell
npx --yes @redocly/cli lint "docs/api/openapi.yaml"
```

并执行以下自检：

- `openapi.yaml` 不包含 `kb_ids`。
- `openapi.yaml` 不定义 `/workspaces` 的创建、列表或切换接口。
- `openapi.yaml` 不定义 OpenAI Embedding 创建路径。
- `API.md` 中列出的所有 API 路径都存在于 `openapi.yaml`。
- 错误结构、SSE 事件、任务状态与 OpenAPI schema 一致。
