# TRD：企业内部 LLM Wiki 知识库系统

> 版本：v1.1
> 日期：2026-08-27
> 状态：草案
> 配套文档：[PRD-LLM-Wiki知识库系统.md](./PRD-LLM-Wiki知识库系统.md)、[architecture.md](./architecture.md)
> 变更：v1.1 — 基于 PRD/TRD 交叉审查，对齐产品与技术描述偏差（GraphRAG 策略、原子性、页面格式等）

---

## 1. 概述

本文档为 LLM Wiki 知识库系统的技术需求文档（TRD），描述系统架构、技术选型、数据库设计、核心流程、API 设计和部署方案。

### 1.1 技术决策汇总

| 项 | 决策 |
|---|---|
| 后端框架 | FastAPI（Python 3.12+，async） |
| 前端框架 | React 18 + Vite + TypeScript |
| UI 组件库 | HeroUI（基于 Tailwind CSS v4 + React Aria） |
| 图谱可视化 | ECharts |
| ORM | SQLAlchemy 2.0（async） |
| 数据库迁移 | Alembic |
| 关系数据库 | PostgreSQL 16 + pgvector + pg_bigm |
| 缓存/任务队列 | Redis 7 + ARQ |
| 认证 | JWT（access + refresh token）+ bcrypt |
| LLM | OpenAI、DeepSeek |
| Embedding | Ollama 本地、OpenAI API |
| 可观测性 | Langfuse（自托管） |
| 流式输出 | SSE（问答）/ 轮询（Wiki ingest） |
| 部署 | Docker Compose |
| Wiki ingest | 结构化六阶段流水线（非 ReAct 自由循环） |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器（React SPA）                     │
│  知识库管理 │ Wiki浏览器 │ 知识图谱(ECharts) │ 问答对话 │ 管理后台  │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼──────────────────────────────────────────┐
│                   FastAPI 后端                            │
│                                                          │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 知识库   │ │ 文档/分块 │ │ Wiki 流水线│ │ RAG 问答管线  │ │
│  │ 管理     │ │ 管理     │ │ (6阶段)   │ │ (事件插件链)  │ │
│  └────┬─────┘ └────┬─────┘ └─────┬────┘ └──────┬───────┘ │
│       │            │             │              │         │
│  ┌────▼────────────▼─────────────▼──────────────▼───────┐ │
│  │              服务层（Services）                        │ │
│  │  LLM Provider │ Embedding │ 检索引擎 │ 图谱 │ 审计     │ │
│  └────┬──────────────────┬──────────────────────────────┘ │
│       │                  │                               │
│  ┌────▼─────┐     ┌──────▼──────┐    ┌─────────────────┐ │
│  │ Langfuse │     │  ARQ Worker │    │  安全/权限中间件  │ │
│  │ 埋点SDK  │     │  (异步任务)  │    │                 │ │
│  └──────────┘     └─────────────┘    └─────────────────┘ │
└───────┬──────────────────┬───────────────────────────────┘
        │                  │
┌───────▼────────┐  ┌──────▼──────────────────────────────┐
│   PostgreSQL   │  │            Redis                     │
│  pgvector      │  │  任务队列 │ 缓存 │ 分布式锁           │
│  pg_bigm       │  └─────────────────────────────────────┘
│  业务数据       │
└────────────────┘
        ▲
        │ gRPC/HTTP（可选扩展：独立解析服务）
┌───────┴────────┐
│  Ollama 本地    │  ← Embedding 模型
│  （用户自行部署） │
└────────────────┘

外部 API：OpenAI / DeepSeek（LLM 调用）
```

### 2.2 架构原则

1. **流水线而非自由 Agent**：Wiki ingest 使用固定六阶段流水线，每阶段职责单一、可独立观测
2. **事件插件链**：RAG 问答管线按固定阶段拆分，每个检索/处理阶段实现为插件，可插拔
3. **异步优先**：文档解析、Wiki ingest 等长任务全部走 ARQ 异步队列，API 立即返回任务 ID
4. **可观测优先**：所有 LLM 调用、检索、Agent 步骤均接入 Langfuse，trace ID 贯穿全链路
5. **模块化**：LLM Provider、Embedding Provider、检索器均为抽象接口，可扩展

> 架构视图：系统上下文、服务边界和 Mermaid 图见 [architecture.md#3-系统上下文与服务边界](./architecture.md#3-系统上下文与服务边界)。

---

## 3. 项目结构

```
knowweave/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # 配置管理（pydantic-settings）
│   │   ├── database.py              # SQLAlchemy async engine/session
│   │   ├── deps.py                  # FastAPI 依赖注入
│   │   ├── api/                     # 路由层
│   │   │   ├── auth.py              # 注册/登录/刷新token
│   │   │   ├── workspaces.py        # 团队/成员管理
│   │   │   ├── knowledge_bases.py   # 知识库 CRUD
│   │   │   ├── documents.py         # 文档上传/列表/删除
│   │   │   ├── wiki.py              # Wiki 页面/版本/图谱
│   │   │   ├── chat.py              # 问答（SSE 流式）
│   │   │   ├── tasks.py             # 异步任务状态查询
│   │   │   └── admin.py             # 模型配置/审计日志
│   │   ├── models/                  # SQLAlchemy 模型
│   │   │   ├── user.py
│   │   │   ├── workspace.py
│   │   │   ├── knowledge_base.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── wiki.py
│   │   │   ├── graph.py
│   │   │   ├── chat.py
│   │   │   └── audit.py
│   │   ├── schemas/                 # Pydantic 请求/响应模型
│   │   ├── services/                # 业务逻辑
│   │   │   ├── auth_service.py
│   │   │   ├── workspace_service.py
│   │   │   ├── kb_service.py
│   │   │   ├── document_service.py
│   │   │   ├── chunking/            # 分块
│   │   │   │   ├── base.py          # Chunker 抽象接口
│   │   │   │   ├── markdown_chunker.py  # Header 路径感知切块
│   │   │   │   └── text_chunker.py  # 纯文本递归切块
│   │   │   ├── embedding/           # Embedding
│   │   │   │   ├── base.py
│   │   │   │   ├── ollama_provider.py
│   │   │   │   └── openai_provider.py
│   │   │   ├── llm/                 # LLM
│   │   │   │   ├── base.py
│   │   │   │   ├── openai_provider.py
│   │   │   │   └── deepseek_provider.py
│   │   │   ├── retrieval/           # 检索
│   │   │   │   ├── dense.py         # pgvector 向量检索
│   │   │   │   ├── sparse.py        # pg_bigm BM25 检索
│   │   │   │   ├── graph.py         # GraphRAG 实体扩展
│   │   │   │   ├── fusion.py        # RRF 融合
│   │   │   │   └── retriever.py     # 多路混合检索编排
│   │   │   ├── wiki/                # Wiki 流水线
│   │   │   │   ├── pipeline.py      # 六阶段编排
│   │   │   │   ├── extract.py       # 阶段1：实体/概念抽取
│   │   │   │   ├── citation.py      # 阶段2：chunk 引用标注
│   │   │   │   ├── taxonomy.py      # 阶段3：分类规划
│   │   │   │   ├── summary.py       # 阶段4：来源摘要页生成
│   │   │   │   ├── reduce.py        # 阶段5：归并写入
│   │   │   │   ├── postprocess.py   # 阶段6：后处理
│   │   │   │   ├── prompts.py       # 所有 Wiki Prompt 模板
│   │   │   │   └── page_service.py  # Wiki 页面 CRUD + 版本
│   │   │   ├── chat/                # 问答管线
│   │   │   │   ├── pipeline.py      # 事件插件链编排
│   │   │   │   ├── plugins/         # 插件
│   │   │   │   │   ├── query_understand.py
│   │   │   │   │   ├── search.py
│   │   │   │   │   ├── merge.py
│   │   │   │   │   ├── filter_topk.py
│   │   │   │   │   └── completion.py
│   │   │   │   └── memory.py        # 对话历史管理
│   │   │   └── observability.py     # Langfuse 封装
│   │   ├── workers/                 # ARQ 异步任务
│   │   │   ├── settings.py          # Worker 配置
│   │   │   ├── tasks.py             # 任务函数
│   │   │   └── main.py              # Worker 入口
│   │   ├── security.py              # JWT/密码/权限
│   │   └── prompts/                 # 通用 Prompt 模板
│   │       ├── rewrite.py           # 查询改写
│   │       ├── qa.py                # 问答系统 Prompt
│   │       └── fallback.py
│   ├── alembic/                     # 数据库迁移
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/                     # API 调用层
│   │   ├── components/              # 通用组件
│   │   │   ├── ui/                  # HeroUI 封装与通用组件
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── CitationPopover.tsx
│   │   │   └── WikiGraph.tsx        # ECharts 图谱封装
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── KnowledgeBaseList.tsx
│   │   │   ├── KnowledgeBaseDetail.tsx
│   │   │   ├── WikiBrowser.tsx
│   │   │   ├── WikiPageEditor.tsx
│   │   │   ├── WikiGraph.tsx
│   │   │   ├── Chat.tsx
│   │   │   ├── Settings.tsx
│   │   │   └── AuditLog.tsx
│   │   ├── stores/                  # Zustand 状态管理
│   │   ├── lib/                     # 工具函数
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js           # Tailwind CSS v4 / HeroUI 配置入口
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 4. 数据库设计

### 4.1 ER 关系总览

```
users ──< workspace_members >── workspaces
workspaces ──< knowledge_bases
knowledge_bases ──< documents
documents ──< chunks
chunks ──< chunk_embeddings（或嵌入 chunks 表）

knowledge_bases (wiki) ──< wiki_source_bindings >── knowledge_bases (document)
knowledge_bases (wiki) ──< wiki_pages
wiki_pages ──< wiki_page_revisions
knowledge_bases ──< entities
entities ──< relations（自引用多对多）

workspaces ──< sessions
sessions ──< messages
workspaces ──< audit_logs
```

### 4.2 核心表结构

#### 4.2.1 users（用户）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| username | VARCHAR(64) UNIQUE NOT NULL | 登录名 |
| password_hash | VARCHAR(255) NOT NULL | bcrypt |
| created_at | TIMESTAMPTZ | |

#### 4.2.2 workspaces（团队）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR(128) NOT NULL | |
| created_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |

#### 4.2.3 workspace_members（团队成员）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| user_id | UUID FK | |
| role | VARCHAR(16) | admin / editor / viewer |
| created_at | TIMESTAMPTZ | |
| | UNIQUE(workspace_id, user_id) | |

#### 4.2.4 knowledge_bases（知识库）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| name | VARCHAR(128) | |
| description | TEXT | |
| type | VARCHAR(16) | document / wiki |
| embedding_model | VARCHAR(64) | 如 ollama:bge-m3 / openai:text-embedding-3-small |
| embedding_dim | INTEGER | 向量维度，创建时确定 |
| chunking_config | JSONB | chunk_size, chunk_overlap, strategy |
| wiki_config | JSONB | llm_model, temperature, llm_timeout, llm_max_retries, auto_ingest（仅 wiki 类型） |
| status | VARCHAR(16) | active / building / disabled |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

#### 4.2.5 wiki_source_bindings（Wiki-Source 绑定）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| wiki_kb_id | UUID FK | |
| source_kb_id | UUID FK | |
| created_at | TIMESTAMPTZ | |
| | UNIQUE(wiki_kb_id, source_kb_id) | |

#### 4.2.6 tags（标签）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| name | VARCHAR(64) | |
| | UNIQUE(workspace_id, name) | |

#### 4.2.7 documents（文档）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| kb_id | UUID FK | |
| filename | VARCHAR(256) | |
| file_hash | CHAR(64) | SHA-256，KB 内唯一 |
| file_path | VARCHAR(512) | 存储路径 |
| file_size | BIGINT | 字节 |
| status | VARCHAR(16) | pending / processing / completed / failed |
| error_message | TEXT | 失败原因 |
| chunk_count | INTEGER | |
| created_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| | UNIQUE(kb_id, file_hash) | 哈希去重 |

#### 4.2.8 document_tags（文档-标签关联）

| 字段 | 类型 |
|---|---|
| document_id | UUID FK |
| tag_id | UUID FK |
| | PK(document_id, tag_id) |

#### 4.2.9 chunks（分块）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| document_id | UUID FK | |
| kb_id | UUID FK | 冗余，方便按 KB 检索 |
| content | TEXT NOT NULL | chunk 文本 |
| header_path | JSONB | 标题路径数组，如 ["产品介绍","计费方式"] |
| seq | INTEGER | 文档内序号 |
| start_pos | INTEGER | 原文起始字符位置 |
| end_pos | INTEGER | 原文结束字符位置 |
| embedding | VECTOR(dim) | pgvector 向量，维度由 KB 配置决定 |
| fts_vector | tsvector | pg_bigm 全文检索向量（基于 content + header_path） |
| chunk_type | VARCHAR(16) | text / wiki_page（Wiki 页面也作为 chunk 入库） |
| source_page_id | UUID FK → wiki_pages NULLABLE | Wiki 页面 chunk 关联 |
| created_at | TIMESTAMPTZ | |

索引：
- `ivfflat` 或 `hnsw` 索引 on `embedding`（cosine）
- GIN 索引 on `fts_vector`（pg_bigm）
- B-tree on `(kb_id, document_id, seq)`

#### 4.2.10 wiki_pages（Wiki 页面）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| kb_id | UUID FK | |
| slug | VARCHAR(256) | 如 entity/tencent、concept/rag、source/doc-xxx |
| title | VARCHAR(256) | |
| page_type | VARCHAR(16) | index / source / entity / concept / overview / analysis |
| summary | TEXT | 一句话摘要（SUMMARY 行） |
| content | TEXT | 当前版本 Markdown 正文（不含 SUMMARY 行） |
| category_path | JSONB | 分类路径，如 ["组织"]、["技术","AI"]，最多 2 级 |
| aliases | JSONB | 别名数组 |
| source_refs | JSONB | 来源文档 ID 数组 |
| current_revision_id | UUID FK → wiki_page_revisions | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| | UNIQUE(kb_id, slug) | |

#### 4.2.11 wiki_page_revisions（页面修订快照）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| page_id | UUID FK | |
| content | TEXT NOT NULL | 该版本完整 Markdown（含 SUMMARY） |
| editor_type | VARCHAR(16) | agent / manual |
| editor_id | UUID FK → users NULLABLE | agent 时为 NULL |
| change_summary | TEXT | 变更说明 |
| created_at | TIMESTAMPTZ | |

索引：`(page_id, created_at DESC)`

#### 4.2.12 entities（实体）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| kb_id | UUID FK | |
| name | VARCHAR(256) | |
| slug | VARCHAR(256) | 与 wiki_pages.slug 对应 |
| entity_type | VARCHAR(32) | person / org / product / place / tech / event / other |
| description | TEXT | |
| wiki_page_id | UUID FK → wiki_pages NULLABLE | 关联的 Wiki 页面 |
| created_at | TIMESTAMPTZ | |
| | UNIQUE(kb_id, slug) | |

#### 4.2.13 relations（实体关系）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| kb_id | UUID FK | |
| source_entity_id | UUID FK → entities | |
| target_entity_id | UUID FK → entities | |
| relation_type | VARCHAR(64) | 属于/包含/相关/合作/竞争... |
| source_chunk_id | UUID FK → chunks | 出处 |
| created_at | TIMESTAMPTZ | |
| | UNIQUE(source_entity_id, target_entity_id, relation_type) | |

#### 4.2.14 sessions（会话）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| user_id | UUID FK | |
| title | VARCHAR(256) | 自动生成 |
| kb_ids | JSONB | 选中的知识库 ID 数组 |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

#### 4.2.15 messages（消息）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK | |
| role | VARCHAR(16) | user / assistant |
| content | TEXT | |
| citations | JSONB | 引用来源数组 |
| trace_id | VARCHAR(64) | Langfuse trace ID |
| token_usage | JSONB | prompt/completion/total tokens |
| created_at | TIMESTAMPTZ | |

#### 4.2.16 audit_logs（审计日志）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| user_id | UUID FK NULLABLE | 系统操作为 NULL |
| action | VARCHAR(64) | document.upload / wiki.ingest / wiki.page_edit / member.invite... |
| resource_type | VARCHAR(32) | document / wiki_page / kb / member... |
| resource_id | UUID NULLABLE | |
| details | JSONB | 操作详情 |
| created_at | TIMESTAMPTZ | |

#### 4.2.17 task_pending_ops（异步任务追踪）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| kb_id | UUID FK | |
| task_type | VARCHAR(32) | document_process / wiki_ingest |
| payload | JSONB | 任务参数（文档 ID 列表等） |
| status | VARCHAR(16) | pending / claimed / completed / failed |
| claimed_by | VARCHAR(128) NULLABLE | Worker 标识 |
| claimed_at | TIMESTAMPTZ NULLABLE | |
| completed_at | TIMESTAMPTZ NULLABLE | |
| error | TEXT NULLABLE | |
| created_at | TIMESTAMPTZ | |

---

## 5. 核心流程设计

### 5.1 文档上传与处理流程

```
用户上传文件（.md/.txt）
    │
    ▼
API 层：
  1. 校验文件类型（仅 .md/.txt）
  2. 计算 SHA-256 哈希
  3. 查 documents 表 (kb_id, file_hash) → 重复则返回 409
  4. 存储文件到本地磁盘（uploads/{kb_id}/{doc_id}.md）
  5. 创建 document 记录（status=pending）
  6. 入队 ARQ 任务 process_document
  7. 返回 document（status=pending）
    │
    ▼
ARQ Worker（process_document）：
  1. 更新 status=processing
  2. 读取文件内容
  3. 选择 Chunker：
     - .md → MarkdownChunker（header 路径感知）
     - .txt → TextChunker（递归字符切分）
  4. 执行分块，得到 List[Chunk]
  5. 批量生成 Embedding（调用配置的 Embedding Provider）
  6. 生成 fts_vector（content + header_path 拼接）
  7. 批量写入 chunks 表（含 embedding、fts_vector）
  8. 更新 document status=completed, chunk_count=N
  9. 若该 KB 绑定了 Wiki KB 且 wiki_config.auto_ingest=true：
     入队 wiki_ingest 任务（debounce 30 秒）
  10. 失败则 status=failed，记录 error_message，支持重试
```

**哈希去重说明**：SHA-256 在同一 KB 内查重。不做文档版本链，内容不同即新文档。

### 5.2 Header 路径感知分块算法

#### 5.2.1 MarkdownChunker

```
输入：Markdown 文本，chunk_size=512，overlap=80
输出：List[Chunk]

算法：
1. 按行扫描，识别标题行（正则 ^(#{1,3})\s+(.+)$）
2. 维护 header_path 状态：
   - H1 → path = [H1标题]
   - H2 → path = [最近H1, H2标题]（无 H1 时 path = [H2标题]）
   - H3 → path = [最近H1, 最近H2, H3标题]
3. 按标题边界切节：每个标题到下一个同级/上级标题之间为一个 section
4. 每个 section 记录其 header_path
5. 若 section 文本长度 > chunk_size：
   在 section 内按段落（\n\n）→ 句子（。！？；）递归切分
   所有子 chunk 共享该 section 的 header_path
6. 相邻 chunk 间保留 overlap 字符（标题边界处不重叠）
7. 为每个 chunk 分配 seq、start_pos、end_pos
```

**Embedding 输入拼接**：
```python
embed_input = " > ".join(chunk.header_path) + "\n" + chunk.content
```

**BM25 全文索引拼接**：
```python
fts_text = " > ".join(chunk.header_path) + " " + chunk.content
```

#### 5.2.2 TextChunker

纯文本无标题结构：
1. 按段落（`\n\n`）→ 句子（`。！？；\n`）递归切分
2. chunk_size=512，overlap=80
3. header_path = `[]`

> 架构视图：文档上传、去重、分块、向量化和自动触发 Wiki ingest 的完整流程见 [architecture.md#6-文档上传与处理架构](./architecture.md#6-文档上传与处理架构)。

### 5.3 Wiki Ingest 六阶段流水线

Wiki ingest 采用六阶段流水线，完整保留独立的 chunk 引用标注阶段和来源摘要页生成阶段。

```
wiki_ingest 任务触发（手动/自动 debounce）
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 阶段 0：准备                                         │
│  - 获取待处理文档列表（task_pending_ops 中 claimed）  │
│  - 获取 Wiki KB 已有所有 slug（slug 连续性用）         │
│  - 获取已有分类目录（taxonomy 复用）                   │
│  - Redis 分布式锁：wiki:ingest:{kb_id}（防并发）      │
└──────────────────────┬──────────────────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 1：抽取（Extract）              │
    │  对每篇文档：                        │
    │  - 读取文档内容（截断 32KB）          │
    │  - 拼接已有 slug 列表                │
    │  - LLM 调用 WikiCandidateSlugPrompt │
    │  - 输出：{entities:[...], concepts:[...]} │
    │  - 每个 item 含 name/slug/aliases/  │
    │    description/details              │
    │  - slug 连续性：相同实体复用旧 slug   │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 2：Chunk 引用标注（Citation）   │
    │  对每篇文档：                        │
    │  - 获取该文档所有 chunk（带 ID）      │
    │  - 将 chunk 分批（每批 ~20 个，      │
    │    确保不超过 LLM 上下文窗口）        │
    │  - 每批 LLM 调用 WikiChunkCitation-  │
    │    Prompt，输入候选 slugs + chunks   │
    │  - 输出：{citations:{slug:[cid]},   │
    │    new_slugs:[...]}                 │
    │  - 合并所有批次结果                  │
    │  - new_slugs 补充进候选列表          │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 3：分类规划（Taxonomy Plan）    │
    │  - 收集本批次所有新 slug             │
    │  - 获取已有文件夹/分类列表           │
    │  - 单次 LLM 调用 WikiTaxonomyPlan-  │
    │    Prompt                           │
    │  - 输出：{assignments:[{slug,path}]}│
    │  - path 最多 2 级，复用已有文件夹    │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 4：来源摘要页（Summary）        │
    │  对每篇文档：                        │
    │  - 读取文档内容（截断 32KB）          │
    │  - 传入阶段1抽取的可用 slug 列表      │
    │    （含 display name + aliases）     │
    │  - LLM 调用 WikiSummaryPrompt       │
    │  - 输出：SUMMARY 行 + Markdown 摘要  │
    │    （含 Key Takeaways，自动加双链）  │
    │  - 创建/更新 source/{doc_id} 页面    │
    │  - 创建 wiki_page_revision 快照     │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 5：归并写入（Reduce）           │
    │  对每个 entity/concept slug          │
    │  （串行，按 slug 加锁）：            │
    │  - 收集该 slug 被引用的所有 chunk    │
    │    原文（verbatim）                  │
    │  - 读取已有页面内容（如存在）         │
    │  - 构造合法链接白名单（所有 slug）    │
    │  - LLM 调用 WikiPageModifyPrompt    │
    │  - 输出：SUMMARY 行 + 更新后 Markdown│
    │  - 创建/更新 wiki_page              │
    │  - 创建 wiki_page_revision 快照     │
    │  - 写入 entities/relations          │
    │  - 应用 taxonomy category_path      │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ 阶段 6：后处理（Post-process）       │
    │  6a. 双链注入：                      │
    │      扫描所有页面内容，将匹配的实体/  │
    │      概念名包裹为 [[slug|名称]]      │
    │  6b. 死链清理：                      │
    │      检查 [[slug]] 指向的页面是否存在│
    │  6c. 内部引用标记剥离：              │
    │      移除 [c001] 等内部 chunk ID    │
    │  6d. 更新/生成 overview.md：         │
    │      基于所有 source 摘要生成全局综述 │
    │  6e. 更新 index.md：                 │
    │      按 category_path 分组列出所有页 │
    │  6f. 所有新/更新页面重新向量化        │
    │      （写入 chunks 表，chunk_type=  │
    │      wiki_page）                     │
    │  6g. 去重检查：                      │
    │      表面相似度预筛 → LLM 判断合并   │
    └──────────────────┬──────────────────┘
                       │
                       ▼
              标记任务完成，记录审计日志
```

#### 5.3.1 上下文管理关键参数

| 参数 | 值 | 说明 |
|---|---|---|
| max_document_content | 32 KB | 单文档进入 LLM 的内容上限 |
| chunks_per_citation_batch | ~20 | 引用标注每批 chunk 数（根据模型上下文窗口调整） |
| max_reduce_chars | 8000 | 归并阶段引用 chunk 原文总字符上限 |
| wiki_ingest_debounce | 30 秒 | 自动触发时的合并窗口 |
| llm_timeout | 60 秒 | 单次 LLM 调用超时 |
| llm_max_retries | 3 | LLM 调用失败重试次数（429 限流固定 backoff 60 秒） |

#### 5.3.2 并发控制

- 同一 Wiki KB 同时只允许一个 ingest 任务（Redis 锁 `wiki:ingest:{kb_id}`）
- 不同 Wiki KB 可并行
- 阶段 5 归并按 slug 加锁（`wiki:slug:{kb_id}:{slug}`），防止同一页面并发写入冲突
- LLM 调用支持重试（429 限流时 backoff 60 秒）
- 任务状态写入 `task_pending_ops` 表，支持崩溃恢复（claim 超过 90 分钟视为 stale，可重新 claim）

#### 5.3.3 原子性与失败处理

`task_pending_ops` 以文档为粒度持久化，`dedup_key` 使用知识库 ID，采用以下策略：

- **Per-slug 事务**：阶段 5 归并写入单个 slug 时，在一个数据库事务中完成 wiki_page upsert + wiki_page_revision 插入 + entities/relations upsert，保证单个页面的原子性
- **Per-document 任务追踪**：`task_pending_ops` 以文档为粒度记录状态（payload 含 doc_id），而非整个批次一个状态。一篇文档失败不影响其他文档
- **部分成功可接受**：已成功生成的页面保留并立即可用，不回滚。失败的文档标记为 failed，用户可单独重试
- **不追求全局事务**：整个 ingest 批次不包在一个大事务中，避免长事务和大量 LLM 调用期间持锁
- **幂等重试**：重试时按 slug 做 upsert（已有页面走归并更新路径），不会产生重复页面

#### 5.3.4 Prompt 设计要点

所有 Wiki Prompt 遵循以下设计原则：

- **WikiCandidateSlugPrompt**：只抽骨架（name/slug/aliases/description/details），不写完整事实；传入 previous_slugs 保证连续性
- **WikiChunkCitationPrompt**：输入候选 slugs + 一批 chunk，输出每个 slug 引用了哪些 chunk ID；可发现 new_slugs；静态指令在前、chunks 在后以利用 prompt cache
- **WikiTaxonomyPlanPrompt**：输入已有文件夹 + 新条目列表，输出每个条目的 category_path；强制复用已有文件夹标签
- **WikiSummaryPrompt**（阶段4）：每篇文档单独调用，输入文档内容（截断 32KB）+ 阶段1抽取的可用 slug 列表（含 display name + aliases），输出 SUMMARY 行 + Markdown 摘要（含 Key Takeaways），自动加 `[[slug|名称]]` 双链；不传文件名（避免无意义文件名导致幻觉）
- **WikiPageModifyPrompt**（System + User，阶段5）：
  - System：共享规则（溯源、禁止幻觉、编译者角色、链接规则、冲突处理）
  - User：页面元数据 + 已有内容 + 新信息（verbatim chunk）+ 合法链接白名单
  - 首行必须输出 `SUMMARY: ...`
- **WikiIndexIntroPrompt / Update**：index 页引言生成/更新

> 架构视图：Wiki ingest 六阶段流水线、Redis 锁、per-slug 事务和 task_pending_ops 关系见 [architecture.md#7-wiki-ingest-架构](./architecture.md#7-wiki-ingest-架构)。

### 5.4 多路混合检索

#### 5.4.1 检索架构

```python
class HybridRetriever:
    """三路并行检索 + RRF 融合"""

    async def retrieve(self, query: str, kb_ids: list[str], top_k: int = 8):
        # 1. 生成 query embedding
        query_embedding = await self.embedding_service.embed(query)

        # 2. 三路并行检索
        dense_results = await self.dense_search(query_embedding, kb_ids, top_k=20)
        sparse_results = await self.sparse_search(query, kb_ids, top_k=20)
        graph_results = await self.graph_search(query, kb_ids, top_k=20)

        # 3. RRF 融合
        fused = self.rrf_fuse(dense_results, sparse_results, graph_results, k=60)

        # 4. Wiki 页面 boost
        fused = self.apply_wiki_boost(fused, boost=1.2)

        # 5. Top-K 截断
        return fused[:top_k]
```

#### 5.4.2 Dense 向量检索（pgvector）

```sql
SELECT c.id, c.content, c.header_path, c.document_id, c.chunk_type,
       1 - (c.embedding <=> :query_embedding) AS score
FROM chunks c
WHERE c.kb_id = ANY(:kb_ids)
ORDER BY c.embedding <=> :query_embedding
LIMIT :top_k;
```

- 使用 cosine distance（`<=>`）
- HNSW 索引，M=16, ef_construction=64

#### 5.4.3 Sparse BM25 检索（pg_bigm）

```sql
SELECT c.id, c.content, c.header_path, c.document_id, c.chunk_type,
       bigm_similarity(c.content, :query) AS score
FROM chunks c
WHERE c.kb_id = ANY(:kb_ids)
  AND c.content &@~ :query
ORDER BY score DESC
LIMIT :top_k;
```

- pg_bigm 提供二元分词，中文无需额外词典
- `&@~` 是 pg_bigm 的模糊全文搜索操作符
- header_path 拼入 content 一起建索引

#### 5.4.4 GraphRAG 图谱检索

Wiki 模式下实体/概念页本身已作为 chunk 入索引，向量+BM25 检索能自然命中相关 Wiki 页面。图谱检索定位为**补充召回**，而非必需路径；当图遍历召回不足时，主检索链路仍由向量检索和 BM25 保证可用性。

```
1. 从 query 中字符串匹配实体名/别名（遍历 entities 表，检查 query 是否包含 entity.name 或 aliases）
2. 对匹配到的实体，沿 relations 表扩展 1 跳关联实体
3. 获取关联实体对应的 wiki_page chunks（source_page_id 关联）
4. 返回结果作为补充召回参与 RRF 融合
```

- 查询时不做 LLM 实体抽取，避免额外延迟和成本
- 图谱扩展范围为 1 跳关联实体
- 图检索无命中时不影响主流程，向量+BM25 仍可正常召回 Wiki 页面

#### 5.4.5 RRF 融合

```python
def rrf_fuse(self, *result_lists, k: int = 60, wiki_boost: float = 1.2):
    scores = {}  # chunk_id -> fused_score
    for results in result_lists:
        for rank, chunk in enumerate(results):
            score = 1.0 / (k + rank + 1)
            if chunk.chunk_type == "wiki_page":
                score *= wiki_boost
            scores[chunk.id] = scores.get(chunk.id, 0) + score

    # 按融合分数排序
    return sorted(scores.items(), key=lambda x: -x[1])
```

- RRF k=60（默认值）
- Wiki 页面 chunk 加权 1.2（预综合内容优先）
- 同一块在多路中同时出现，分数累加

> 架构视图：Dense、Sparse、GraphRAG、RRF 和 Wiki boost 的整体检索流程见 [architecture.md#8-检索与-rag-问答架构](./architecture.md#8-检索与-rag-问答架构)。

### 5.5 RAG 问答管线

#### 5.5.1 事件插件链

问答过程为固定阶段插件链：

```
用户提问（SSE 连接建立）
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1. LOAD_HISTORY                             │
│    加载最近 10 轮对话历史                     │
├─────────────────────────────────────────────┤
│ 2. QUERY_UNDERSTAND                         │
│    LLM 调用：将多轮指代改写为独立查询          │
│    （coreference resolution）                │
│    同时判断意图：kb_search / greeting /      │
│    chitchat（闲聊直接回答，跳过检索）          │
├─────────────────────────────────────────────┤
│ 3. CHUNK_SEARCH_PARALLEL                    │
│    三路并行检索（dense + sparse + graph）    │
│    SSE 推送进度："正在检索知识库..."          │
├─────────────────────────────────────────────┤
│ 4. CHUNK_MERGE                              │
│    - 同文档相邻 chunk 合并（去 overlap）      │
│    - 去重（ID/内容哈希）                     │
│    - 组装 header_path 面包屑                 │
├─────────────────────────────────────────────┤
│ 5. FILTER_TOP_K                             │
│    - 阈值过滤（低于相似度阈值的丢弃）         │
│    - 取 Top-8 进入 LLM 上下文               │
│    - 无结果 → fallback 提示                 │
├─────────────────────────────────────────────┤
│ 6. INTO_CHAT_MESSAGE                        │
│    组装 Prompt：                             │
│    - System：你是知识库助手，基于以下         │
│      上下文回答，必须标注引用来源...          │
│    - Context：带编号的检索片段               │
│    - History：最近 10 轮                     │
│    - User：改写后的查询                      │
├─────────────────────────────────────────────┤
│ 7. CHAT_COMPLETION_STREAM                   │
│    LLM 流式生成，SSE 逐 token 推送           │
│    完成后推送 citations（引用来源列表）       │
└─────────────────────────────────────────────┘
```

#### 5.5.2 引用溯源

- 检索片段进入 LLM 上下文时带编号 `[1]`、`[2]`...
- System Prompt 要求 LLM 在回答中使用 `[1]` 角标引用
- 引用元数据：document_id、filename、header_path、chunk 内容片段
- 前端渲染：角标可 hover 显示来源卡片，点击跳转到原文/Wiki 页面
- Wiki 页面来源和原始文档来源用不同图标区分

#### 5.5.3 SSE 事件格式

```
event: progress
data: {"stage": "search", "message": "正在检索知识库..."}

event: progress
data: {"stage": "merge", "message": "正在整理相关内容..."}

event: token
data: {"content": "根据"}

event: token
data: {"content": "文档"}

event: done
data: {
  "message_id": "uuid",
  "citations": [
    {"id": 1, "document_id": "...", "filename": "产品手册.md",
     "header_path": ["计费方式"], "snippet": "..."}
  ],
  "trace_id": "langfuse-trace-id"
}
```

#### 5.5.4 对话历史管理

- 保留最近 10 轮（20 条消息）
- 超出 10 轮的历史不进入上下文
- QUERY_UNDERSTAND 阶段用最近 3 轮做指代改写

> 架构视图：RAG 问答 SSE sequenceDiagram 和事件插件链关系见 [architecture.md#8-检索与-rag-问答架构](./architecture.md#8-检索与-rag-问答架构)。

### 5.6 知识图谱构建

图谱在 Wiki ingest 阶段 5（Reduce）中随页面写入同步构建：

```
归并写入某个 entity/concept 页面时：
  1. upsert entity（按 slug 唯一）
  2. LLM 在归并输出中同时返回关系列表（结构化 JSON，与页面正文分离）
  3. 对每条关系：
     - 查找/创建 target entity
     - upsert relation（source, target, type, source_chunk_id）
```

- 关系抽取依赖归并 LLM 在生成页面内容时同时输出关系列表（JSON 结构，非 Markdown frontmatter）
- 关系类型为自由文本（属于/包含/相关/合作/竞争/使用/位于...）
- 图谱可视化：ECharts，支持力导向布局、缩放拖拽、点击节点跳转 Wiki 页面、按类型筛选

> 架构视图：Wiki 页面、entities/relations、ECharts 可视化和 GraphRAG 召回关系见 [architecture.md#9-wiki-页面与知识图谱架构](./architecture.md#9-wiki-页面与知识图谱架构)。

---

## 6. API 设计

### 6.1 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/register | 注册（同时创建团队） |
| POST | /api/auth/login | 登录，返回 access/refresh token |
| POST | /api/auth/refresh | 刷新 token |

### 6.2 团队与成员

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/workspaces | 我的团队列表 |
| POST | /api/workspaces | 创建团队 |
| GET | /api/workspaces/{id}/members | 成员列表 |
| POST | /api/workspaces/{id}/members | 邀请成员 |
| PATCH | /api/workspaces/{id}/members/{user_id} | 修改角色 |
| DELETE | /api/workspaces/{id}/members/{user_id} | 移除成员 |

### 6.3 知识库

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/kbs | 知识库列表（可按 type 筛选） |
| POST | /api/kbs | 创建知识库 |
| GET | /api/kbs/{id} | 知识库详情 |
| PATCH | /api/kbs/{id} | 更新设置（分块配置、Wiki 配置） |
| DELETE | /api/kbs/{id} | 删除知识库 |
| POST | /api/kbs/{id}/bind | 绑定 Source KB（Wiki KB 专用） |
| DELETE | /api/kbs/{id}/bind/{source_kb_id} | 解绑 |

### 6.4 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/kbs/{id}/documents/upload | 上传文件（multipart），支持批量 |
| GET | /api/kbs/{id}/documents | 文档列表（分页、标签筛选、搜索） |
| GET | /api/documents/{id} | 文档详情（含 chunk 列表） |
| DELETE | /api/documents/{id} | 删除文档 |
| POST | /api/documents/{id}/retry | 重试失败的解析任务 |
| GET | /api/kbs/{id}/tags | 标签列表 |
| POST | /api/kbs/{id}/tags | 创建标签 |

### 6.5 Wiki

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/wiki/{kb_id}/ingest | 触发 Wiki 生成/更新 |
| GET | /api/wiki/{kb_id}/status | Wiki ingest 任务状态 |
| GET | /api/wiki/{kb_id}/pages | Wiki 页面列表（按分类树） |
| GET | /api/wiki/pages/{id} | 页面详情（当前版本） |
| PUT | /api/wiki/pages/{id} | 编辑页面（人工） |
| GET | /api/wiki/pages/{id}/revisions | 版本历史列表 |
| GET | /api/wiki/pages/{id}/revisions/{rev_id} | 查看指定版本 |
| GET | /api/wiki/pages/{id}/diff | 对比两个版本（query: from, to） |
| POST | /api/wiki/pages/{id}/rollback | 回滚到指定版本 |
| GET | /api/wiki/{kb_id}/graph | 知识图谱数据（节点+边） |
| POST | /api/wiki/{kb_id}/rebuild | 全量重建（管理员） |

### 6.6 问答

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/chat/sessions | 创建会话 |
| GET | /api/chat/sessions | 会话列表 |
| GET | /api/chat/sessions/{id}/messages | 消息历史 |
| GET | /api/chat/sessions/{id}/stream | SSE 流式问答（query: question, kb_ids） |
| DELETE | /api/chat/sessions/{id} | 删除会话 |
| PATCH | /api/chat/sessions/{id} | 重命名会话 |

### 6.7 管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/admin/models | 模型配置 |
| PUT | /api/admin/models | 更新模型配置（API Key、Base URL） |
| POST | /api/admin/models/test | 测试模型连通性 |
| GET | /api/admin/audit-logs | 审计日志（分页、筛选） |

---

## 7. 异步任务设计

### 7.1 ARQ 任务定义

| 任务名 | 触发 | 参数 | 说明 |
|---|---|---|---|
| process_document | 文档上传 | doc_id | 分块+向量化 |
| wiki_ingest | 手动/自动 | kb_id, doc_ids[] | Wiki 六阶段流水线 |
| wiki_ingest_debounced | 自动上传后 | kb_id | 延迟 30 秒入队 wiki_ingest |

### 7.2 任务状态追踪

- 不依赖 ARQ 内置状态，使用 PostgreSQL `task_pending_ops` 表持久化
- Worker claim 任务时更新 status=claimed、claimed_by、claimed_at
- 完成更新 status=completed，失败更新 status=failed + error
- 前端通过 `GET /api/wiki/{kb_id}/status` 轮询任务进度
- 进度阶段：pending → extracting → citing → taxonomy → summarizing → reducing → postprocessing → completed

### 7.3 重试与错误处理

- ARQ 内置重试（最多 3 次，指数退避）
- LLM 429 限流：固定等待 60 秒后重试
- 任务失败后用户可在 UI 手动重试
- 致命错误（如 LLM 返回非法 JSON）记录到 task_pending_ops.error，不自动重试

---

## 8. 安全设计

### 8.1 认证与授权

- 密码 bcrypt 哈希（cost=12）
- JWT access token 有效期 30 分钟，refresh token 7 天
- 所有 API 除 register/login 外需携带 access token
- 团队资源访问校验中间件：从 JWT 提取 user_id → 查 workspace_member → 校验角色

### 8.2 数据隔离

- 所有查询强制带 workspace_id 条件
- 知识库访问校验：用户必须是该 KB 所属团队的成员
- Wiki KB 只能绑定同团队的 Source KB

### 8.3 敏感信息

- LLM/Embedding API Key 加密存储（AES-256-GCM，密钥从环境变量读取）
- API 响应中不返回明文 API Key（只返回掩码 + 是否已配置）
- Langfuse 公钥/密钥同样加密

### 8.4 文件上传

- 仅允许 .md/.txt 扩展名
- 限制单文件大小（默认 10MB，可配置）
- 文件名消毒（防止路径穿越）
- 文件存储在 Docker volume 中，不暴露为静态资源（通过 API 鉴权访问）

> 架构视图：认证、RBAC、workspace 隔离、敏感信息和文件安全边界见 [architecture.md#10-安全与权限架构](./architecture.md#10-安全与权限架构)。

---

## 9. 可观测性设计

### 9.1 Langfuse 集成

所有关键操作创建 Langfuse trace/span：

| 操作 | Trace | Span |
|---|---|---|
| 文档处理 | `document_process` | chunking、embedding |
| Wiki ingest | `wiki_ingest` | extract、citation（每文档）、taxonomy、summary（每文档）、reduce（每slug）、postprocess |
| 问答 | `chat_qa` | query_understand、search（dense/sparse/graph）、merge、completion |
| LLM 调用 | （子 span） | model、prompt、response、tokens、cost、latency |

- 每个 trace 携带 workspace_id、kb_id、user_id 作为 metadata
- 问答响应中返回 trace_id，管理员可在 Langfuse UI 中查看完整链路
- Wiki ingest 每阶段的 LLM 输入/输出均记录，方便调试生成质量

### 9.2 日志

- Python 标准 logging + structlog（JSON 结构化日志）
- 日志级别通过环境变量配置
- 关键操作记录到 audit_logs 表（业务审计）

> 架构视图：Langfuse trace/span、结构化日志和 audit_logs 分层见 [architecture.md#11-可观测性架构](./architecture.md#11-可观测性架构)。

---

## 10. 部署架构

### 10.1 Docker Compose 服务

```yaml
services:
  db:           # PostgreSQL 16 + pgvector + pg_bigm
    image: pgvector/pgvector:pg16
    # 需要在镜像中安装 pg_bigm 扩展（自定义 Dockerfile）
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:        # Redis 7
    image: redis:7-alpine

  langfuse:     # Langfuse 自托管（web + worker）
    image: langfuse/langfuse:2
    depends_on: [db, redis]

  backend:      # FastAPI
    build: ./backend
    depends_on: [db, redis, langfuse]
    env_file: .env
    volumes:
      - ./uploads:/app/uploads

  worker:       # ARQ Worker
    build: ./backend
    command: arq app.workers.main.WorkerSettings
    depends_on: [db, redis]
    env_file: .env
    volumes:
      - ./uploads:/app/uploads

  frontend:     # React SPA（nginx 托管）
    build: ./frontend
    depends_on: [backend]
    ports:
      - "80:80"

volumes:
  pgdata:
```

### 10.2 pg_bigm 安装

PostgreSQL 镜像需要自定义 Dockerfile 安装 pg_bigm：

```dockerfile
FROM pgvector/pgvector:pg16
RUN apt-get update && apt-get install -y postgresql-16-pgbigm
```

初始化时执行 `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_bigm;`

### 10.3 Ollama

- Ollama 由用户在宿主机或独立服务器自行部署
- 通过 `OLLAMA_BASE_URL` 环境变量配置地址
- 推荐 Embedding 模型：`bge-m3`（1024 维）或 `nomic-embed-text`（768 维）
- docker-compose 中可添加 `network_mode: host` 或 `extra_hosts: host.docker.internal:host-gateway` 访问宿主机 Ollama

### 10.4 环境变量（.env.example）

```
# Database
DATABASE_URL=postgresql+asyncpg://openwiki:openwiki@db:5432/openwiki

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Encryption
ENCRYPTION_KEY=base64-encoded-32-byte-key

# LLM
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Embedding
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_EMBED_MODEL=bge-m3
OPENAI_EMBED_MODEL=text-embedding-3-small

# Langfuse
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# Storage
UPLOAD_DIR=/app/uploads
MAX_FILE_SIZE_MB=10

# App
DEFAULT_CHUNK_SIZE=512
DEFAULT_CHUNK_OVERLAP=80
WIKI_MAX_DOC_CONTENT_KB=32
WIKI_INGEST_DEBOUNCE_SECONDS=30
RETRIEVAL_TOP_K=8
RRF_K=60
CHAT_HISTORY_TURNS=10
```

> 架构视图：Docker Compose 部署拓扑、服务依赖和环境变量分组见 [architecture.md#12-docker-compose-部署架构](./architecture.md#12-docker-compose-部署架构)。

---
