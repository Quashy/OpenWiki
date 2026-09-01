# 知衍 KnowWeave v1 开发路线图

> 版本：v2.10
> 日期：2026-08-29
> 状态：开发基线
> 来源：[PRD](../PRD-LLM-Wiki知识库系统.md)、[TRD](../TRD-LLM-Wiki知识库系统.md)、[Architecture](../architecture.md)、[API](../api/API.md)
> 变更：v2.10 — 在不改变 M5 已完成口径的前提下，补充 WeKnora 检索链路对标与 M7 检索质量演进候选；Rerank、MMR 去冗余、父子/邻接 chunk 上下文扩展、多 KB / 多存储 fanout、Web Search 并行均不属于当前 v1 demo 必需范围。

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
  -> 固化 Wiki Prompt 质量
  -> 浏览 Wiki / 图谱
  -> 单 KB RAG 问答
  -> 编辑、版本、审计与观测（demo 后）
```

**Demo 定义**：M0-M5 为 demo 主线，**M5 退出门禁通过即可对外演示**（上传 → 生成 → Prompt 质量固化 → 浏览/图谱 → 问答带引用的完整链路）。M6 为 demo 后的工程补齐，M7 为演进。

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

以下 TRD 工程项在 demo 阶段（M2-M5）简化实现，M6 补齐。这是有意的收敛，不是遗漏：

| TRD 工程项 | demo 阶段处理 | 补齐位置 |
|---|---|---|
| Redis 分布式锁 `wiki:ingest:{kb_id}` + per-slug 锁 | 不实现；单 worker 串行执行 + `task_pending_ops` 状态检查保证"同一 Wiki KB 同时只有一个 ingest" | M6 |
| 任务崩溃恢复（claim 超时 90 分钟视为 stale 可回收） | 不做；失败任务走手动重试 | M6 |
| LLM 429 限流固定 60 秒 backoff + ARQ 指数退避 | 普通重试即可 | M6 |
| 性能指标（PRD 5.1 全表） | 不验证 | M6 单用户自查 / M7 并发 |
| 审计日志查询界面 | 只写不查（M1 已交付写入基础设施，随写接口顺带保留） | M6 |
| 20 人并发问答 | 不做 | M7 |

### 2.2 PRD 功能后置清单

以下 PRD 功能明确后置到 M7，由真实需求触发，不在 v1 demo 主线上：

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

Langfuse 在 v1 中优先用于 LLM/RAG 业务链路追踪和质量分析，不替代 Prometheus/Grafana 类系统监控。M2-M5 按链路逐步补齐 trace/span，M6 统一验收以下 dashboard 方向：

- 文档摄入健康度：上传数、处理成功率、失败率、embedding 耗时、chunk 数、失败原因。
- Wiki Prompt 质量：抽取噪音、引用命中、归并失败、Dedup 决策、prompt version。
- RAG 问答质量：query、召回 chunk、引用命中率、回答评分、无答案率。
- 成本与性能：模型调用次数、token、耗时 P50/P95，并按模型、KB 维度拆分。

### 2.4 检索链路开源对标与演进方向

当前 M5 已完成的 v1 demo 检索链路为：单 `kb_id` 范围内 Query Rewrite -> Dense（pgvector）/Sparse（pg_bigm）/GraphRAG 三路召回 -> RRF 融合 -> Wiki page boost -> Top-8 -> 引用 grounding -> SSE 回答。该链路满足 demo 闭环，但仍是偏轻量的检索实现。

以 Tencent WeKnora 当前开源实现为参考，其 RAG 检索链路包含更完整的工程增强：QueryUnderstand 做改写与意图识别；知识库检索与 Web Search 可并行；多 KB / 多向量库按 embedding model 与 store 分组 fanout；Vector + Keyword 混合召回后使用 RRF；低召回时可 query expansion；融合后进入 rerank model；rerank 后做阈值过滤、阈值降级兜底、composite score、FAQ boost 与 MMR 去冗余；随后执行父子 chunk 解析、邻接 chunk 扩展、连续片段合并、重复/重叠内容去重，最后再 TopK 截断并组装引用。

知衍 KnowWeave 后续检索演进按收益/复杂度分层处理：

- M6 不扩大检索范围，优先完成工程补齐、观测闭环、固定语料验收和单用户性能自查；若 QA 失败明确指向上下文过短或重复，可做最小修复。
- M7 优先候选：`RRF Top 20/30 -> Rerank -> MMR -> Top 8`，并增加父子/邻接 chunk 上下文扩展；引用仍指向原命中 chunk，避免溯源语义变复杂。
- M7 视真实需求再考虑：多 KB 联合问答、多存储 fanout、Web Search 并行、FAQ 专用 boost、query expansion、图谱检索增强。
- 不直接照搬 WeKnora 的完整 agent pipeline；只有当现有 QA eval 或试用数据证明召回、排序、去冗余、上下文完整性存在稳定问题时，才进入实现。

## 3. 里程碑总览

状态只使用：`未开始`、`进行中`、`阻塞`、`已完成`。

| 里程碑 | 用户能力 | demo 定位 | 状态 | 主要完成证据 |
|---|---|---|---|---|
| M0 | 工程与契约基线可启动、可迁移、可校验 | — | 已完成 | 2026-08-27：迁移、OpenAPI lint、前后端基础检查通过 |
| M1 | 注册登录、管理成员与模型配置、创建/绑定 KB | — | 已完成 | 2026-08-27：RBAC、模型探测、KB 骨架和前端 M1 外壳测试通过 |
| M2 | 上传文档、打标签、查看分块与处理状态 | demo 第一步 | 已完成 | 2026-08-28：上传、分块、向量化、检索基线、文档处理 trace 通过 |
| M3 | 触发 Wiki 生成，浏览页面与知识图谱 | demo 第二步 | 已完成 | 2026-08-28：六阶段 ingest、页面浏览、图谱交互、真实 DeepSeek trace 和自动化检查通过 |
| M4 | Wiki Prompt 评估框架与生成质量固化 | demo 质量门禁 | 进行中 | Micro Eval 已有 10 个 case；Scenario Eval 已有 3 个生活场景包、18 个文档、18 个问题并通过结构静态校验；当前接受版本 `wiki_prompt_v0.3` 已接入 6 个现有阶段与 Dedup，并记录 prompt version trace；`wiki_prompt_v0.4` 已因指标回退撤回；不做完整验收，剩余为 Scenario Eval runner、质量报告和 QA 反馈驱动的质量修复 |
| M5 | 单 KB 问答，流式回答带引用可溯源 | 🎯 demo 达成 | 已完成 | 2026-08-29：方案 B 完成；单 KB 会话/API、SSE、三路检索 + RRF、引用角标/详情、Markdown 渲染、Langfuse trace、QA runner 与 Docker 集成测试通过 |
| M6 | 编辑 Wiki、版本回滚、审计查询、观测闭环 | demo 后工程补齐 | 未开始 | 编辑、版本、审计、Langfuse 闭环、全量回归通过 |
| M7 | 检索质量、多 KB / Web Search 等真实需求驱动演进 | 演进 | 未开始 | 由试用数据、QA eval 或明确需求触发；优先候选为 Rerank、MMR 去冗余、父子/邻接 chunk 上下文扩展 |

## 4. 里程碑明细

里程碑详细内容已按阶段拆分到独立文档，ROADMAP 只保留总览、全局口径、接口完成定义和 PRD 功能追踪矩阵。

| 里程碑 | 明细文档 |
|---|---|
| M0 | [M0：工程与契约基线（已完成）](./M0.md) |
| M1 | [M1：账号、团队、模型配置、KB 骨架（已完成）](./M1.md) |
| M2 | [M2：Source KB 文档摄入闭环](./M2.md) |
| M3 | [M3：Wiki 生成、浏览与知识图谱](./M3.md) |
| M4 | [M4：Wiki Prompt 评估框架与生成质量固化](./M4.md) |
| M5 | [M5：单 KB RAG 问答（🎯 Demo 达成）](./M5.md) |
| M6 | [M6：工程补齐（Demo 后）](./M6.md) |
| M7 | [M7：v1 后演进](./M7.md) |

## 5. 接口完成定义

一个接口只有同时满足以下条件，才算完成：

- OpenAPI schema、后端实现、前端调用保持一致（契约一致性由 Redocly lint 全局保障）。
- 后端执行认证、Workspace 隔离和 RBAC 校验（由共享依赖统一实现并集中测试）。
- 写接口完成真实数据库写入、审计日志和事务边界。
- 长任务接口返回任务 ID，并能通过 `GET /tasks/{task_id}` 查询稳定状态。
- 前端页面不使用永久 mock 数据。

测试策略：后端只保留两类 pytest 测试——横切关注点冒烟（认证/RBAC/审计各覆盖一次）与固定语料管线测试（分块、召回、Wiki 后处理）；前端不编写测试，以 tsc 构建、页面手动走查验收。

## 6. PRD 功能追踪矩阵

里程碑列标注所属阶段和当前状态：M0-M3 已完成，M4 进行中且暂不完整验收，M5 已完成，M6 工程补齐，M7 演进。"v1 处理"列取值 `v1` 或 `部分`（注明收敛、质量债或后置点，详见表 2.1 / 2.2）。

| PRD 章节 | 功能 | v1 处理 | 里程碑 |
|---|---|---|---|
| 4.1.1 | 注册与登录（首用户建团成 Admin） | v1 | M1（已完成） |
| 4.1.2 | 团队管理（成员/角色/重命名） | 部分：多团队创建/切换后置 | M1（已完成） |
| 4.1.3 | 审计日志（写入） | v1 | M1（已完成） |
| 4.1.3 | 审计日志（查询界面、按类型/时间筛选） | v1 | M6 |
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
| 4.5.1 | wiki_config（LLM 模型、超时、重试、温度） | 部分：auto_ingest 后置 | M3（已完成） |
| 4.5.2 | Wiki 页面类型（六类页面） | v1 | M3（已完成） |
| 4.5.3 | 页面内容结构（元信息字段 + SUMMARY 行 + 双链） | v1 | M3（已完成） |
| 4.5.4 | Wiki 生成触发（手动、互斥、全量重建） | 部分：自动触发 + debounce 后置 | M3（已完成） |
| 4.5.5 | 六阶段流水线（Extract/Citation/Taxonomy/Summary/Reduce/Post-process） | v1 | M3（已完成） |
| 4.5.5 | Wiki Prompt 工程化（评估框架、确定性指标、模板抽取、版本、Dedup、质量回归） | 部分：Micro Eval、Prompt 接入、Dedup 已落地；Scenario runner 与 QA 反馈驱动质量修复保留为 M4 质量债 | M4（进行中，暂不完整验收） |
| 4.5.6 | Wiki 页面浏览（目录树、双链、来源跳转、搜索） | v1 | M3（已完成） |
| 4.5.7 | Wiki 页面编辑（修订快照、重新向量化、人工编辑提示） | v1 | M6 |
| 4.5.8 | 版本管理（历史、diff、回滚） | v1 | M6 |
| 4.5.9 | 知识图谱（entities/relations 存储、Reduce 构建） | v1 | M3（已完成） |
| 4.5.9 | 图谱可视化（ECharts 缩放/拖拽/跳转/筛选） | v1 | M3（已完成） |
| 4.6.1 | 问答入口（对话界面、选择知识库） | 部分：单 KB 收敛，多选后置；真实会话/API 和前端入口已完成 | M5（已完成） |
| 4.6.2 | 多路混合检索（三路并行 + RRF + Wiki boost） | v1：Dense/Sparse/GraphRAG 三路召回、RRF、Wiki boost、阈值过滤已完成 | M5（已完成） |
| 4.6.2 | 检索质量增强（Rerank、MMR 去冗余、父子/邻接 chunk 上下文扩展、query expansion） | 部分：参考 WeKnora 等开源实现作为 M7 候选；不纳入 M5 完成口径，需由 QA eval 或试用数据触发 | M7 |
| 4.6.3 | RAG 问答流程（改写、检索、流式、进度） | v1：历史加载、查询改写、检索、流式回答、AI 气泡内进度已完成 | M5（已完成） |
| 4.6.4 | 引用溯源（角标、来源列表、跳转、类型区分） | v1：角标联动、引用详情、Wiki 跳转、Markdown 渲染已完成；原文精确定位后置 | M5（已完成） |
| 4.6.4 | QA 评估（复用 Wiki eval questions、召回/引用/无答案指标） | v1：M5 QA runner 与指标输出已完成；Wiki 质量失败继续回流 M4 | M5（已完成） |
| 4.6.5 | 多轮对话（改写、10 轮窗口、持久化） | 部分：标题自动生成后置；历史持久化和查询改写已完成 | M5（已完成） |
| 4.6.6 | 会话管理（列表、重命名、删除、范围记录） | 部分：推荐问题后置；列表、重命名、删除已完成 | M5（已完成） |
| 4.7 | 观测：文档解析进度 trace | v1 | M2（已完成） |
| 4.7 | 观测：Wiki 流水线六阶段 trace | v1 | M3（已完成） |
| 4.7 | 观测：Wiki Prompt version 与阶段质量 trace | 部分：Micro Eval trace 已落地；Scenario 真实报告与 QA 反馈回流保留为质量债 | M4（进行中，暂不完整验收） |
| 4.7 | 观测：LLM 调用链路 + 检索过程 trace、trace_id 返回 | v1：`chat_qa` trace 与 SSE done `trace_id` 已完成 | M5（已完成） |
| 4.7 | 观测：面板访问、trace 搜索、token/成本排序闭环 | v1 | M6 |
| 4.7 | 观测：系统指标（队列深度、错误率） | 部分：后置 | M7 |
| 4.8.1 | LLM 模型配置（OpenAI/DeepSeek、加密、测试） | v1 | M1（已完成） |
| 4.8.2 | Embedding 配置（Ollama 发现/探测） | 部分：OpenAI Embedding 与多维向量后置 | M1（已完成） |
| 5.1 | 性能（首 token、解析、ingest、检索） | 部分：M6 单用户自查，并发后置 | M6、M7 |
| 5.2 | 安全（bcrypt、AES、隔离、上传限制、审计） | v1：随里程碑实现，M6 集中验证 | M1-M2（已完成）、M3-M5、M6 |
| 5.3 | 部署（Docker Compose、持久化卷） | v1：M0 基线，M6 空库部署演练 | M0（已完成）、M6 |
| 5.4 | 可用性（失败隔离、重试、部分成功） | v1 | M2（已完成）、M3 |
| 5.5 | 国际化（界面中文） | v1 | 全程 |

## 7. 维护规则

- 开始里程碑时在 ROADMAP 总览和 PRD 功能追踪矩阵中将状态改为 `进行中`；完成后在 ROADMAP 总览和对应 `Mx.md` 附测试或验收证据。
- 日常开发按改动范围运行最快相关检查；里程碑退出时执行必要验收，不强制静态检查门禁。
- OpenAPI、Docker、数据库迁移只在相关文件变化时触发专项检查。
- 范围变化必须先更新 ROADMAP、对应 `Mx.md` 和 OpenAPI，再改实现。
- PRD/TRD 与 ROADMAP 或里程碑文件冲突时，先确认是否属于 v1 收敛或 demo 简化（见 2.1 / 2.2）；确认后同步修改相关文档。
- 不为后续里程碑保留永久空实现；提前实现的接口也必须满足所属里程碑的完成定义。
