# OpenWiki V2 v1 开发演进路线图

> 版本：v1.0
> 日期：2026-08-27
> 状态：已确认
> 适用范围：OpenWiki V2 v1 的设计、开发、测试与内部试用验收
> 来源文档：[PRD](../PRD-LLM-Wiki知识库系统.md)、[TRD](../TRD-LLM-Wiki知识库系统.md)、[Architecture](../architecture.md)

---

## 1. 文档定位

本文档是 OpenWiki V2 v1 的开发与验收基线，用于把完整产品目标拆分为可连续交付、可独立验收的纵向里程碑。

### 1.1 文档优先级

当文档之间存在冲突时，按以下顺序执行：

1. 本 ROADMAP 中明确冻结的 v1 范围、裁剪项、接口差异和验收门禁。
2. [PRD](../PRD-LLM-Wiki知识库系统.md) 中的产品语义、用户行为与功能要求。
3. [TRD](../TRD-LLM-Wiki知识库系统.md) 中的技术选型、数据模型与 API 目标。
4. [Architecture](../architecture.md) 中的系统边界、数据流与目标部署架构。

未被本 ROADMAP 明确覆盖或裁剪的需求，继续以 PRD、TRD 和 Architecture 为准，不得仅因未出现在某个里程碑的摘要中而省略。

### 1.2 推进原则

- **纵向切片**：每个里程碑同时交付所需的数据库、后端、前端和自动化测试，不采用“后端全部完成后再统一开发前端”的方式。
- **门禁推进**：里程碑只有在退出条件全部满足后才能标记完成。
- **主干可运行**：已完成能力必须接入真实数据和真实接口；允许未来页面暂不存在，不允许用永久 mock 或空实现伪装完成。
- **无日历承诺**：路线图不写日期、人日或周数，以可验证结果作为唯一进度刻度。
- **完整后试用**：M0—M6 全部完成后才开放 v1 内部试用，不以部分主链路代替 v1 验收。
- **显式变更**：范围、接口或门禁变化必须先更新本文件，禁止实现与路线图长期分叉。

---

## 2. v1 目标与冻结边界

### 2.1 v1 目标

v1 要交付一个面向单团队的完整 LLM Wiki 知识库系统：团队成员可以管理多个 Source KB 和 Wiki KB，摄入原始文档，通过六阶段流水线生成并持续更新 Wiki，在单个物理知识库范围内使用三路检索完成带引用的问答，并使用编辑、版本、图谱、审计与可观测性能力完成内部知识维护闭环。

核心闭环：

```text
注册/加入唯一团队
  → 创建 Source KB 与 Wiki KB
  → 上传、分块、索引原始文档
  → 六阶段 Wiki ingest
  → 浏览 Wiki / 图谱 / 来源
  → 对单个 Source KB 或 Wiki KB 问答
  → 编辑、对比、回滚与审计
```

### 2.2 v1 保留能力

- 账号密码注册登录、JWT access/refresh token、Admin/Editor/Viewer 三级 RBAC。
- 唯一团队内的成员添加、移除、角色调整与团队重命名。
- 多个 Source KB、多个 Wiki KB，以及 Wiki KB 到 Source KB 的多对多绑定。
- Markdown/TXT 文档、批量上传、标签、去重、预览、删除、失败原因与手动重试。
- Header-aware 分块、Ollama Embedding、Dense、Sparse、GraphRAG 与 RRF。
- Extract、Citation、Taxonomy、Summary、Reduce、Post-process 完整六阶段流水线。
- index/source/entity/concept/overview/analysis 六类 Wiki 页面、双链、来源引用和实体关系。
- Wiki 浏览、全文搜索、人工编辑、修订历史、diff、回滚与人工编辑覆盖提示。
- 单知识库会话、查询改写、SSE 流式回答、引用角标、来源跳转与多轮历史。
- 知识图谱数据与交互式图谱视图。
- 审计日志、推荐问题、模型配置后台、结构化日志和 Langfuse 全链路追踪。

### 2.3 v1 冻结约束

#### 账号与团队

- 系统只允许存在一个 Workspace，但保留 `workspaces`、`workspace_members` 和所有业务表的 `workspace_id`，避免未来多团队演进时重构领域模型。
- 首个注册用户在同一事务中创建唯一 Workspace，并成为 Admin。
- 后续用户可以注册账号，但注册后默认不属于团队；Admin 按用户名添加成员并分配角色。
- 系统必须始终保留至少一名 Admin，禁止移除最后一名 Admin 或将其降级。
- 不提供团队创建、团队切换和跨团队访问流程。

#### 知识库与问答范围

- Source KB 与 Wiki KB 继续作为两个独立知识库类型，不合并数据模型。
- Wiki KB 可以绑定一个或多个 Source KB，绑定关系遵循 TRD 的多对多模型。
- 一次会话只关联一个物理 KB，API 使用单值 `kb_id`，拒绝多 KB 参数。
- Source KB 可以直接问答；其 GraphRAG 路径允许返回空结果，但 Dense/Sparse 必须正常执行。
- 选择 Wiki KB 时只检索该 Wiki KB 的页面 chunk，不自动联合检索其绑定的 Source KB。

#### LLM 配置

- 全系统同一时刻只启用一个 LLM 配置，Wiki 生成、查询改写和问答生成共用该配置。
- 后台支持 OpenAI 和 DeepSeek 的 API Key、Base URL、模型参数和连通性测试。
- API Key 使用 AES-256-GCM 加密入库，接口只返回掩码与配置状态，不返回明文。

#### Embedding 配置

- v1 仅支持本地 Ollama，且仅接受实测输出维度为 1024 的 embedding 模型。
- 当前环境已验证以下模型：

| 模型 | 当前 digest 前缀 | 实测维度 | 上下文长度 | v1 定位 |
|---|---|---:|---:|---|
| `bge-m3:latest` | `790764642607` | 1024 | 8192 | 默认模型 |
| `mxbai-embed-large:latest` | `468836162de7` | 1024 | 512 | 可选模型 |

- 创建 KB 时固化 `embedding_model_tag`、完整 `embedding_model_digest` 和 `embedding_dim=1024`，创建后不提供模型切换。
- 模型发现接口必须读取 Ollama capability，并用最小 embedding 请求实测维度；非 embedding 模型或非 1024 维模型不得用于创建 KB。
- 每次写入或查询前校验当前模型 digest。tag 相同但 digest 改变时，将 KB 标记为 embedding 不兼容，停止新增向量和检索，直到管理员完成全量重建。
- `bge-m3:latest` 为默认值，但不得把 `latest` tag 当作稳定模型身份。

#### 长任务与运行形态

- 后端和前端在宿主机本地运行；PostgreSQL、pgvector、pg_bigm、Langfuse 等依赖通过 Docker 启动。
- 文档处理和 Wiki ingest 由后端进程内 Runner 执行，不引入应用级 Redis、ARQ 或独立 Worker。
- Runner 全局 FIFO 串行，同一时刻只执行一个长任务；v1 不实现并发任务和分布式锁。
- `task_pending_ops` 是任务状态事实源。API 创建任务后立即返回任务 ID，前端轮询状态。
- 后端启动时，未开始的 `pending` 任务继续排队；上次进程遗留的 `running` 任务标记为 `failed`，错误类型为 `interrupted`，允许人工重试。
- 自动 ingest 使用数据库 `run_after` 与去重键完成 30 秒 debounce；相同 Wiki KB 的未运行任务合并文档 ID，不依赖 Redis 定时任务。
- 本地开发和部署均固定单个后端进程，不支持多 Uvicorn worker。

### 2.4 v1 明确后置

以下能力不属于 M0—M6 的完成条件，统一进入 M7：

- 多 Workspace、团队切换和真正的跨团队数据隔离场景。
- 任意 Source/Wiki KB 多选与跨 KB RRF 问答。
- OpenAI Embedding、非 1024 维向量及多维索引共存。
- Redis/ARQ、独立 Worker、分布式任务恢复和队列级重试。
- 多任务并发、per-KB/per-slug 分布式锁及 20 人并发目标。
- 前后端容器化、完整生产 Docker Compose 和横向扩容。

---

## 3. 里程碑总览

状态只允许使用：`未开始`、`进行中`、`阻塞`、`已完成`。

| 里程碑 | 目标 | 状态 | 完成证据 |
|---|---|---|---|
| M0 | 工程与质量基线 | 未开始 | 本地启动、迁移和基线测试记录 |
| M1 | 账号、单团队与模型配置 | 未开始 | 权限矩阵和模型探测集成测试 |
| M2 | 源文档摄入闭环 | 未开始 | 文档摄入 E2E 和检索基线 |
| M3 | Wiki 生成与浏览 | 未开始 | 六阶段流水线质量报告 |
| M4 | RAG 问答主链路 | 未开始 | 单 KB 问答与引用 E2E |
| M5 | PRD 功能补齐 | 未开始 | PRD 追踪矩阵无遗漏项 |
| M6 | 内部试用门禁 | 未开始 | 完整验收报告 |
| M7 | 试用后演进 | 未开始 | 由实际瓶颈触发，不阻塞 v1 |

### M0—工程与质量基线

**目标**：建立后续纵向切片共同依赖的可运行工程、可重复数据库和可度量质量样本。

**交付物**：

- FastAPI、React/Vite/TypeScript、SQLAlchemy/Alembic 的最小可运行工程。
- Docker 依赖编排：PostgreSQL 16、pgvector、pg_bigm，以及可选的 Langfuse 观测栈。
- 本地 `.env.example`、配置校验、健康检查和数据库扩展初始化。
- 统一 API 错误结构、结构化日志、请求/任务关联 ID。
- LLM 与 Embedding 调用边界；不为未实现 Provider 建立空壳实现。
- 固定质量语料：重复文档、实体别名、相互矛盾事实、跨文档关系、精确编号和无答案问题。
- 单元、PostgreSQL 集成和核心 E2E 的测试目录与执行命令。

**退出门禁**：

- 一条命令可启动全部依赖，前后端可在本地分别启动。
- Alembic 可从空库升级到当前版本，所需扩展创建成功。
- 健康检查可以识别数据库和 Ollama 不可用状态。
- 固定语料、预期实体、预期引用和预期检索证据已版本化。
- lint、类型检查和初始测试全部通过。

### M1—账号、单团队与模型配置

**目标**：建立真实身份、唯一团队边界、模型配置与知识库领域骨架。

**交付物**：

- 注册、登录、refresh token 和密码哈希。
- 首用户初始化唯一团队，其他账号等待 Admin 添加。
- Admin/Editor/Viewer 权限校验、成员列表、添加、移除和角色调整。
- 禁止最后一名 Admin 被移除或降级。
- 全局 OpenAI/DeepSeek LLM 配置、加密存储、掩码返回与连通性测试。
- Ollama 服务配置、模型发现、embedding capability 过滤、实际维度探测和 digest 展示。
- 多 Source/Wiki KB CRUD、启停、Wiki-Source 绑定与 Embedding 配置固化。
- 审计写入边界从本阶段开始建立，后续所有写操作接入同一服务。
- 对应登录、成员、模型和知识库管理页面。

**退出门禁**：

- 权限矩阵的允许/拒绝场景全部通过 API 集成测试。
- 并发首注册只能产生一个 Workspace 和一个初始 Admin。
- 非成员无法访问任何团队资源，Viewer 无法调用写接口。
- 模型测试不会泄露密钥；非 1024 维或非 embedding 模型无法创建 KB。
- KB 创建后无法修改已固化的模型 tag、digest 和维度。

### M2—源文档摄入闭环

**目标**：完成从文件上传到可检索 chunk 的真实闭环。

**交付物**：

- Markdown/TXT 单文件及批量上传、大小和扩展名校验、文件名消毒。
- SHA-256 KB 内去重、标签、列表、搜索、筛选、排序、详情和原文预览。
- Markdown Header-aware 分块、TXT 递归分块、超长章节二次切分和 overlap。
- 分块预览、header_path、seq、字符位置和 Embedding 输入拼接。
- `task_pending_ops`、进程内 FIFO Runner、任务查询和失败重试。
- Ollama 批量向量化、`vector(1024)`、HNSW，以及基于 content/header_path 的 pg_bigm 稀疏索引。
- 文档删除时同步清理 chunk、向量与检索索引。
- 文档列表和详情实时呈现 pending/running/completed/failed、阶段和错误原因。
- 文档上传、删除、重试等操作写入审计日志和 Langfuse/结构化日志。

**退出门禁**：

- 相同文件在同一 KB 返回冲突，在不同 KB 可以独立存在。
- 固定 Markdown 语料的 header_path、切分边界、overlap 和位置字段符合预期。
- 中断任务在重启后变为可解释的 failed，人工重试不产生重复 chunk。
- Dense 和 Sparse 都能在固定问题的 Top-K 中召回预期证据。
- 删除文档后不能再通过任何检索路径召回其内容。

### M3—Wiki 生成与浏览

**目标**：完整实现可重试、可溯源、可增量演进的六阶段 Wiki。

**交付物**：

- 阶段 1 Extract：抽取实体/概念骨架并复用已有 slug。
- 阶段 2 Citation：分批标注 slug 到 chunk ID 的引用，并合并新发现 slug。
- 阶段 3 Taxonomy：复用已有分类，生成最多两级 category_path。
- 阶段 4 Summary：生成来源摘要页、SUMMARY 和 Key Takeaways。
- 阶段 5 Reduce：按 slug 归并原文证据与已有页面，写入实体关系。
- 阶段 6 Post-process：双链注入、死链清理、内部标记剥离、overview/index 更新、页面重新向量化和去重检查。
- index/source/entity/concept/overview/analysis 六类页面及系统生成的修订快照。
- Wiki 目录树、Markdown 渲染、双链跳转、来源跳转和全文搜索。
- 手动 ingest、30 秒自动 ingest debounce、任务阶段轮询、失败文档重试和全量重建。
- 文档删除后来源页标记“来源已删除”，不自动删除已生成的综合页面。
- 每个 slug 的页面、修订、实体与关系写入使用单事务；不同文档允许部分成功。
- 每阶段 LLM 输入、输出、耗时、token 与错误接入 Langfuse。

**退出门禁**：

- 固定多文档语料能够产生六类页面；分析语料包含足以触发 analysis 页的对比或冲突。
- 所有 `source_refs` 和 Citation chunk ID 指向真实记录。
- 后处理完成后不存在死链和遗留内部 chunk 标记。
- 同一批文档重复 ingest 不产生重复页面、修订外的重复实体或重复关系。
- 单文档失败不回滚其他文档已完成页面，重试能够幂等收敛。
- 全量重建期间 Wiki KB 不可查询，成功后恢复可用。

### M4—RAG 问答主链路

**目标**：完成单物理 KB 范围内可溯源的三路 RAG 问答。

**交付物**：

- 单值 `kb_id` 会话、会话列表、历史、重命名和删除。
- LOAD_HISTORY、QUERY_UNDERSTAND、CHUNK_SEARCH、MERGE、FILTER、PROMPT、STREAM 完整管线。
- pgvector Dense、pg_bigm Sparse、实体别名匹配与一跳扩展 GraphRAG。
- RRF `k=60`、Wiki chunk boost、去重、相邻 chunk 合并和 Top-8。
- Source KB GraphRAG 空结果降级，不影响另外两路结果。
- SSE progress/token/done 事件、回答引用角标、来源卡片和原文/Wiki 跳转。
- 最近十轮对话、最近三轮查询改写、闲聊/问候短路和无结果 fallback。
- 问答消息、citations、token usage 和 trace ID 持久化。

**退出门禁**：

- API 和前端均无法提交多个 KB；会话只能访问创建时绑定的单个 KB。
- 固定语料问题的 Top-8 包含预期证据，回答引用只指向实际进入上下文的片段。
- Source KB 和 Wiki KB 都能独立完成问答，引用图标和跳转目标正确。
- GraphRAG 无命中、LLM 超时、SSE 中断和无检索结果均有明确降级行为。
- 多轮指代问题能够被改写为独立查询，且不会越过会话的 KB 边界。

### M5—PRD 功能补齐

**目标**：补齐不阻塞主链路构建、但属于 v1 完整体验和治理要求的全部能力。

**交付物**：

- Wiki 人工编辑、不可变修订历史、任意版本查看、行级 diff 和以新修订方式回滚。
- 人工编辑后被系统更新时的醒目提示与对比入口。
- @antv/g6 图谱视图、缩放、拖拽、节点跳转及实体/关系类型筛选。
- 推荐问题、完整搜索筛选、失败详情和所有管理页面。
- 审计日志分页、操作类型/时间筛选和不可删除约束。
- Langfuse 文档处理、Wiki ingest、检索和问答的完整 trace/span。
- 模型管理、配置测试、可观测性跳转和错误提示的前端闭环。
- 按第 6 节追踪矩阵逐项核对 PRD，不遗留占位接口或模拟数据页面。

**退出门禁**：

- 自动与人工页面写入都会创建修订，回滚不会删除任何历史。
- 图谱页面与 GraphRAG 使用同一实体/关系事实源。
- 所有 PRD 写操作都生成可查询审计记录。
- 每次问答和 Wiki ingest 都能从业务记录跳转到对应 Langfuse trace。
- 第 6 节除明确后置项外全部具有测试或验收证据。

### M6—内部试用门禁

**目标**：证明 v1 在固定环境中功能完整、结构正确、权限可靠且具备可诊断性。

**交付物**：

- 全量单元、集成、API 契约和核心 E2E 回归报告。
- 固定语料的 Wiki 质量、检索召回和回答引用报告。
- 密钥、认证、授权、文件上传和路径穿越安全检查。
- 单用户文档处理、检索、首 token 和 Wiki ingest 性能基准。
- 安装、启动、模型准备、数据备份和常见失败排查文档。
- PRD 追踪矩阵最终签核和已知限制清单。

**退出门禁**：

- 所有非后置功能和结构性门禁通过。
- 没有阻断主链路或造成数据错误/越权访问的已知缺陷。
- PRD 的单用户性能指标完成实测；20 人并发不作为 v1 门禁。
- 从空数据库按照文档能够独立完成核心 E2E。
- v1 状态由“开发中”更新为“可内部试用”。

### M7—试用后演进

M7 不按预设日期启动，只由实际使用数据触发，详见第 8 节。

---

## 4. 关键接口与数据约束

### 4.1 Workspace 接口

- 使用 `GET /api/workspaces/current` 获取唯一团队，使用 `PATCH /api/workspaces/current` 重命名。
- 成员接口挂在 `/api/workspaces/current/members` 下。
- 不提供创建第二个 Workspace、团队列表或团队切换接口。
- 所有资源查询仍必须携带并校验 `workspace_id`，不得用“当前只有一个团队”作为跳过授权的理由。

### 4.2 Knowledge Base 与 Embedding

`knowledge_bases` 至少固化以下 Embedding 字段：

| 字段 | 约束 |
|---|---|
| `embedding_provider` | v1 固定为 `ollama` |
| `embedding_model_tag` | 创建时选择，之后只读 |
| `embedding_model_digest` | 创建时读取完整 digest，之后用于一致性校验 |
| `embedding_dim` | v1 固定为 `1024` |

- 模型 tag、digest、维度不得通过通用 KB 更新接口修改。
- digest 漂移时 KB 进入不可检索状态，重建完成前不得混合写入新旧向量。
- Wiki 页面使用所属 Wiki KB 固化的 Embedding 配置，不继承绑定 Source KB 的模型。

### 4.3 Chunk 归属

- `chunks.embedding` 使用 `vector(1024)` 并建立 cosine HNSW 索引。
- `document_id` 对 Wiki page chunk 可为空，`source_page_id` 对文档 chunk 可为空。
- 数据库必须使用等价约束保证：

```text
chunk_type = text      → document_id 非空，source_page_id 为空
chunk_type = wiki_page → document_id 为空，source_page_id 非空
```

- Dense 与 Sparse 索引文本都包含 `header_path + content`。

### 4.4 会话与问答

- `sessions` 使用 `kb_id UUID FK`，不使用 `kb_ids JSONB`。
- 创建会话和流式问答 API 只接受一个 `kb_id`，数组或多个参数返回 422。
- 会话创建后不得在消息请求中临时切换 KB；需要切换时创建新会话。

### 4.5 任务状态

`task_pending_ops` 统一使用以下稳定契约：

| 维度 | 约束 |
|---|---|
| `status` | `pending / running / completed / failed` |
| `stage` | 文档或 Wiki 流水线当前阶段，独立于 status |
| `progress` | 0—100，阶段切换和批次处理时更新 |
| `run_after` | 自动 ingest debounce 与延迟执行时间 |
| `dedup_key` | 合并同类未运行任务 |
| `error` | 可面向用户展示的摘要和可诊断错误码 |

- 增加通用 `GET /api/tasks/{task_id}` 状态接口；文档和 Wiki 专用状态接口复用同一事实源。
- 人工重试创建新的 pending 任务并记录来源任务 ID，保留原失败记录和审计链。
- 未来迁移 ARQ 时保持任务创建、查询、状态和重试 API 不变，只替换执行器。

### 4.6 模型发现接口

- 增加 Admin 专用 Ollama 模型发现接口，返回 tag、digest、capability、实测维度和是否可用于 v1。
- 模型测试接口必须区分网络失败、鉴权失败、模型不存在、非 embedding 模型和维度不兼容。
- 全局 LLM 配置沿用 TRD 管理接口，但任意时刻只允许一个活动配置。

### 4.7 里程碑接口落地映射

接口实现顺序由本 ROADMAP 的纵向里程碑决定，`docs/api/openapi.yaml` 作为接口主契约。不得按接口文档顺序机械实现一组薄接口；每个里程碑完成时，对应接口必须接入真实数据、权限、统一错误和自动化测试。

#### M0：工程与契约基线

M0 不绑定具体业务 endpoint，负责建立所有后续接口共同依赖的工程能力：

- OpenAPI lint 与契约测试入口。
- 统一错误响应、请求 ID、结构化日志和认证中间件骨架。
- FastAPI 路由组织、Pydantic schema 分层和 API 集成测试目录。
- 数据库迁移、健康检查和外部依赖可用性检查。

#### M1：账号、单团队、模型配置与知识库骨架

M1 实现身份、唯一 Workspace、成员、模型配置和 KB 基础能力：

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /workspaces/current`
- `PATCH /workspaces/current`
- `GET /workspaces/current/members`
- `POST /workspaces/current/members`
- `PATCH /workspaces/current/members/{user_id}`
- `DELETE /workspaces/current/members/{user_id}`
- `GET /admin/llm-config`
- `PUT /admin/llm-config`
- `POST /admin/llm-config/test`
- `GET /admin/ollama-config`
- `PUT /admin/ollama-config`
- `GET /admin/ollama/models`
- `POST /admin/ollama/models/probe`
- `GET /kbs`
- `POST /kbs`
- `GET /kbs/{kb_id}`
- `PATCH /kbs/{kb_id}`
- `DELETE /kbs/{kb_id}`
- `POST /kbs/{kb_id}/bindings`
- `DELETE /kbs/{kb_id}/bindings/{source_kb_id}`

#### M2：源文档摄入、标签与任务状态

M2 实现从上传文件到可检索 chunk 的闭环，并接入通用任务查询：

- `POST /kbs/{kb_id}/documents/upload`
- `GET /kbs/{kb_id}/documents`
- `GET /documents/{document_id}`
- `DELETE /documents/{document_id}`
- `POST /documents/{document_id}/retry`
- `GET /kbs/{kb_id}/tags`
- `POST /kbs/{kb_id}/tags`
- `PATCH /kbs/{kb_id}/tags/{tag_id}`
- `DELETE /kbs/{kb_id}/tags/{tag_id}`
- `POST /kbs/{kb_id}/chunk-preview`
- `GET /tasks/{task_id}`

#### M3：Wiki 生成、浏览与图谱数据

M3 实现 Wiki 六阶段生成、页面浏览、页面详情和图谱事实源：

- `POST /wiki/{kb_id}/ingest`
- `POST /wiki/{kb_id}/rebuild`
- `GET /wiki/{kb_id}/pages`
- `GET /wiki/{kb_id}/graph`
- `GET /wiki-pages/{page_id}`

#### M4：单 KB RAG 问答主链路

M4 实现单物理 KB 会话、历史和 SSE 流式问答：

- `POST /chat/sessions`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}/messages`
- `GET /chat/sessions/{session_id}/stream`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`

#### M5：PRD 补齐项与治理接口

M5 补齐 Wiki 人工维护、版本治理、审计和图谱交互验收：

- `PUT /wiki-pages/{page_id}`
- `GET /wiki-pages/{page_id}/revisions`
- `GET /wiki-pages/{page_id}/revisions/{revision_id}`
- `GET /wiki-pages/{page_id}/diff`
- `POST /wiki-pages/{page_id}/rollback`
- `GET /admin/audit-logs`
- 对 `GET /wiki/{kb_id}/graph` 补齐前端缩放、拖拽、节点跳转和筛选验收。

#### M6：内部试用门禁

M6 不新增接口，负责全量契约、权限、安全、性能、E2E 和 PRD 追踪矩阵验收。

#### 接口完成规则

- 对应 OpenAPI 请求和响应 schema 必须对齐，不能只满足前端当前调用。
- RBAC 必须由后端强校验，不能只依赖前端隐藏入口。
- 写接口必须接入真实数据库写入、审计日志和统一错误结构。
- 依赖外部模型的接口必须使用真实连通性测试或可复现 stub 测试。
- API 集成测试必须覆盖成功路径、权限拒绝路径和关键业务拒绝路径。
- 禁止把后续里程碑接口做成永久 mock；若提前实现后续接口，必须同时满足该接口所属里程碑的最低契约和测试要求。
- `docs/api/openapi.yaml` 是接口 schema 主契约，本节只记录落地顺序，不重复定义请求和响应结构。

---

## 5. 测试与质量策略

### 5.1 自动化测试分层

- **单元测试**：分块、overlap、RRF、双链解析、死链清理、diff、权限矩阵、模型 capability/维度/digest 校验。
- **数据库集成测试**：迁移、HNSW、pg_bigm、上传幂等、级联删除、任务恢复、per-slug 事务、修订和审计。
- **API 契约测试**：认证、RBAC、单 Workspace、单 `kb_id`、错误结构、SSE 事件和任务状态。
- **LLM Stub 测试**：非法 JSON、超时、阶段失败、部分成功、重试、重复 ingest 和无结果 fallback。
- **真实模型回归**：固定语料的实体、概念、引用、页面、Top-K 证据和带引用回答。
- **核心 E2E**：管理员初始化与加人 → 创建 Source/Wiki KB → 上传文档 → 六阶段生成 → Wiki/图谱浏览 → 单 KB 问答 → 编辑、diff、回滚 → 审计追踪。

### 5.2 固定语料要求

固定语料至少覆盖：

- 内容完全相同但文件名不同的文档。
- 中文/英文别名、同名实体和 slug 复用。
- 两篇文档对同一事实给出冲突描述。
- 需要跨文档归并才能回答的问题。
- 精确编号、产品名和专有术语，验证 Sparse 路径。
- 一跳实体关系问题，验证 GraphRAG。
- 知识库中没有答案的问题，验证 fallback 和禁止幻觉。

### 5.3 结构性门禁

- 所有引用记录可解析并指向真实 chunk 或 Wiki 页面。
- Post-process 完成后双链无死链、正文无内部 chunk 标记。
- 重复 ingest 不产生重复页面、实体或关系。
- 页面每次自动写入、人工编辑和回滚都有不可变修订记录。
- 删除文档后原始 chunk 不可检索，已摄入来源页显示来源删除状态。
- 所有越权请求均被后端拒绝，不能只依赖前端隐藏入口。
- API Key、token 和文档内容不得出现在非受控日志中。

### 5.4 性能基准

在记录硬件、模型 tag/digest、语料规模和配置的固定环境中测量：

- 问答首 token 延迟目标 `< 2 秒`。
- 100 KB Markdown 文档处理目标 `< 10 秒`。
- 单文档 Wiki ingest 目标 `< 60 秒`，单独标注外部 LLM 耗时。
- 单 KB 三路检索目标 `< 1 秒`。
- 20 人并发目标明确后置，不作为 v1 试用门禁。

---

## 6. PRD 需求追踪矩阵

| PRD 需求 | v1 决策 | 里程碑 | 最低验收证据 |
|---|---|---|---|
| 4.1 注册与登录 | 保留 | M1 | 首用户初始化、后续用户登录、token 刷新测试 |
| 4.1 团队管理 | 单团队裁剪 | M1 | 当前团队、成员与角色 E2E；无多团队入口 |
| 4.1 审计日志 | 保留 | M1/M5 | 写操作审计覆盖表与筛选页面 |
| 4.2 Source KB 管理 | 保留多 KB | M1/M2 | CRUD、启停、搜索筛选测试 |
| 4.2 文档标签 | 保留 | M2 | 标签 CRUD、绑定与筛选测试 |
| 4.3 文档管理 | 保留 | M2 | 上传、批量、去重、详情、删除、重试 E2E |
| 4.4 文档分块 | 保留 | M2 | Header-aware/文本分块固定样本测试 |
| 4.5.1 Wiki KB 与绑定 | 保留多对多 | M1 | 绑定/解绑和类型校验测试 |
| 4.5.2—4.5.5 页面与 ingest | 完整六阶段 | M3 | 六阶段 trace、页面/关系/修订验证 |
| 4.5.6 Wiki 浏览 | 保留 | M3 | 目录、双链、搜索、来源跳转 E2E |
| 4.5.7—4.5.8 编辑与版本 | 保留 | M5 | 编辑、diff、回滚和覆盖提示 E2E |
| 4.5.9 知识图谱 | 保留 | M3/M5 | 实体关系一致性和 G6 交互测试 |
| 4.6.1 问答 KB 选择 | 裁剪为单物理 KB | M4 | 多 KB 请求拒绝、Source/Wiki 独立问答 |
| 4.6.2 三路混合检索 | 保留 | M4 | 三路结果、RRF 排名和降级测试 |
| 4.6.3—4.6.4 SSE 与引用 | 保留 | M4 | progress/token/done 和引用跳转 E2E |
| 4.6.5—4.6.6 多轮与会话 | 保留 | M4 | 历史、改写、重命名、删除测试 |
| 4.7 可观测性 | 保留 | M0/M3/M4/M5 | trace/span 覆盖和业务跳转验证 |
| 4.8 LLM 模型 | 全局单配置 | M1 | OpenAI/DeepSeek 配置与测试 |
| 4.8 Embedding 模型 | Ollama 1024 维 | M1/M2 | capability、维度、digest 与漂移测试 |
| 5.1 性能 | 单用户指标保留；并发后置 | M6 | 固定环境性能报告 |
| 5.2 安全 | 保留 | M1/M6 | 密码、JWT、RBAC、加密和上传安全测试 |
| 5.3 部署 | 依赖 Docker；应用本地 | M0 | 依赖启动和本地开发文档 |
| 5.4 可用性 | 单进程重试策略 | M2/M3/M6 | 中断恢复、部分成功、重试测试 |
| 5.5 中文界面 | 保留 | 全阶段/M6 | 核心页面和错误文案检查 |

---

## 7. v1 完成定义

只有同时满足以下条件，v1 才能标记为“可内部试用”：

- M0—M6 全部为“已完成”。
- 第 6 节所有非后置项均有可复现的自动化或人工验收证据。
- 核心 E2E 在空数据库上能够从头完成。
- 固定语料的引用、双链、幂等和权限结构性门禁全部通过。
- 不存在会导致数据丢失、错误引用、权限绕过或不可恢复任务状态的已知缺陷。
- 本地安装、运行、备份和故障排查文档完整。
- 三份来源文档保持不变，本文件中的裁剪与覆盖项没有未记录分叉。

---

## 8. M7 恢复条件

后置能力按实际问题触发，禁止仅为“未来可能需要”提前引入：

| 后置能力 | 启动条件 | 演进方向 |
|---|---|---|
| Redis/ARQ 与独立 Worker | 进程重启导致的任务失败不可接受，或排队任务持续积压 | 保持任务 API，替换 Runner 执行器 |
| 并发任务与分布式锁 | 明确需要同时处理多个文档/Wiki 任务 | per-KB ingest 锁、per-slug 锁、幂等 claim |
| 多团队 | 出现第二个真实隔离团队需求 | 开放 Workspace CRUD/切换并补齐隔离测试 |
| 跨 KB 问答 | 单 KB 无法覆盖真实查询范围 | 按 Embedding 身份分组检索后使用 RRF 融合 |
| OpenAI/多维 Embedding | Ollama 不能满足质量、成本或部署需求 | 引入 Embedding profile 与按维度索引/迁移策略 |
| 完整容器部署 | 需要在开发机外稳定部署或交付 | 容器化前后端、独立 Worker、生产 Compose |
| 20 人并发与扩容 | 有真实并发负载和容量目标 | 压测、连接池、缓存、并行检索和水平扩容 |

---

## 9. 路线图维护规则

- 开始里程碑时将状态改为“进行中”，同时登记负责人或任务链接。
- 完成里程碑时附上测试、演示、质量报告或验收记录，不能只修改状态。
- 阻塞超过一个开发周期时记录阻塞原因、影响和解除条件。
- 新需求先映射到现有里程碑；无法映射时必须说明它是 v1 变更还是 M7 候选。
- 任何对冻结范围、数据契约或试用门禁的调整，都必须在实现前更新本文件并重新确认。
