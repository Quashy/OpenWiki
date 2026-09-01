<div align="center">

<h1>知衍 KnowWeave</h1>

<p><strong>把散落的 Markdown / TXT 文档整理成可浏览、可互链、可追溯的团队 Wiki。</strong></p>

<p>
  知衍 KnowWeave 将原始资料与生成结果分开保存，通过多阶段 LLM 流水线生成 Wiki 页面与知识图谱，并在单个知识库范围内提供带引用的流式问答。
</p>

<p>
  <a href="docs/v1/ROADMAP.md"><img src="https://img.shields.io/badge/status-v1%20Demo-2563eb?style=flat-square" alt="项目状态：v1 Demo"></a>
  <a href="docs/v1/M5.md"><img src="https://img.shields.io/badge/demo-M5%20%E5%B7%B2%E5%AE%8C%E6%88%90-16a34a?style=flat-square" alt="Demo 主线：M5 已完成"></a>
  <a href="#快速开始"><img src="https://img.shields.io/badge/deploy-Docker%20Compose-2496ed?style=flat-square&amp;logo=docker&amp;logoColor=white" alt="部署方式：Docker Compose"></a>
</p>

<p>
  <a href="#功能预览">功能预览</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#项目状态与边界">项目状态与边界</a> ·
  <a href="docs/v1/ROADMAP.md">开发路线</a>
</p>

</div>

[![知衍 KnowWeave Wiki 浏览器：目录、生成页面、双链与来源数量](assets/readme/wiki-browser.png)](assets/readme/wiki-browser.png)

> [!NOTE]
> 当前是开发中的 v1 Demo。文档上传、Wiki 生成、页面浏览、知识图谱和单 KB 引用问答已经跑通；Wiki 生成质量评估仍在持续收敛，尚不代表生产就绪。

## 为什么选择知衍 KnowWeave

- **原文留在原文里。** Source KB 保存上传文档、分块与索引，生成内容不会覆盖事实底稿。
- **Wiki 不只是一份报告。** Wiki KB 将跨文档内容整理为分类页面、双链和实体关系，更新后继续参与检索。
- **回答能够回到证据。** 回答正文使用引用角标，并保留命中文档、标题路径、片段与来源类型。

## 功能预览

### 从生成页面回到原始片段

Wiki 浏览器同时提供目录、类型筛选、Markdown 阅读、双链跳转和来源定位。展开来源后，可以查看页面关联的原始文档；存在精确引用时，还可定位到对应 Chunk。

[![知衍 KnowWeave 来源定位：从 Wiki 页面查看原始文档与精确片段](assets/readme/source-traceability.png)](assets/readme/source-traceability.png)

### 探索实体关系

按实体或关系类型筛选 ECharts 力导向图，并从节点继续打开对应 Wiki 页面。

[![知衍 KnowWeave 知识图谱：实体关系网络、筛选器与节点列表](assets/readme/knowledge-graph.png)](assets/readme/knowledge-graph.png)

### 在单个知识库内提问

在单个知识库范围内获得流式回答，并通过引用角标查看命中的原文或 Wiki 片段。

[![知衍 KnowWeave 智能问答：带引用角标的回答与 Wiki 证据卡片](assets/readme/cited-answer.png)](assets/readme/cited-answer.png)

## 从文档到 Wiki

知衍 KnowWeave 把事实底稿和 LLM 生成结果放在两个物理知识库中：一个 Wiki KB 可以绑定多个 Source KB，但生成页面不会反向改写上传的原文。

[![小黑用引用线把原始文档缝合为互链 Wiki，表示原始文档与生成 Wiki 之间保留来源关联](assets/knowweave-readme-illustrations/01-source-to-wiki.png)](assets/knowweave-readme-illustrations/01-source-to-wiki.png)

| 知识库 | 保存内容 | 主要用途 |
| --- | --- | --- |
| **Source KB** | 上传的 Markdown / TXT、Chunk、向量索引与关键词索引 | 保留原始资料和直接检索证据 |
| **Wiki KB** | 来源摘要、实体、概念、综述、分析、分类、双链与实体关系 | 承载跨文档整理结果，用于浏览、图谱和问答 |

核心链路可以概括为：

1. 上传文档，执行格式校验、SHA-256 去重与异步任务登记。
2. 按 Markdown 标题路径分块，同时建立 Dense 与 Sparse 检索表示。
3. 手动触发六阶段 Wiki ingest（Extract → Citation → Taxonomy → Summary → Reduce → Post-process）；候选项在 Extract 后先经过 Dedup。
4. 将生成页面作为 `wiki_page` Chunk 重新向量化并写入统一索引；会话可选择一个 Source KB 或 Wiki KB 进行引用问答。

## 核心能力

| 能力 | 当前实现 |
| --- | --- |
| 文档摄入 | Markdown / TXT 上传、标签、去重、标题路径感知分块、Ollama 1024 维 Embedding 与 pg_bigm 关键词索引 |
| Wiki 生成 | 六阶段流水线、来源摘要、实体与概念页、分类目录、双链、实体关系和生成页面再索引 |
| 知识探索 | 目录搜索、类型筛选、Markdown 渲染、双链跳转、来源定位和交互式知识图谱 |
| 引用问答 | 单 KB 会话、最近 10 轮上下文、查询改写、Dense + Sparse 召回、Wiki KB 补充 GraphRAG、RRF、Top-8、SSE、引用详情与 `trace_id` |
| 团队与观测 | JWT、Admin / Editor / Viewer RBAC、模型配置、任务状态、审计写入和可选 Langfuse Trace |

## 快速开始

### 1. 准备运行环境

Docker Compose 是默认启动方式，需要：

- Docker Desktop；
- 本机运行的 [Ollama](https://ollama.com/)；
- 一个可用的 OpenAI-compatible Chat Completions 接口及其 API Key（当前优先支持 OpenAI / DeepSeek）。

Node.js 22+ 与 Python 3.12+ 只在源码开发时需要。

### 2. 准备配置和 Embedding 模型

```powershell
Copy-Item .env.example .env
ollama pull bge-m3
```

编辑 `.env`，至少替换 `JWT_SECRET`、`ENCRYPTION_KEY`，并配置 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY` 之一。也可以在启动后通过「模型设置」保存 LLM 配置；API Key 会加密入库，接口只返回掩码。

### 3. 启动服务并执行迁移

```powershell
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose ps
```

默认入口：

| 服务 | 地址 |
| --- | --- |
| Web UI | <http://localhost:8080> |
| API Health | <http://localhost:8000/api/v1/health> |
| Swagger UI | <http://localhost:8000/api/v1/docs> |
| Langfuse | <http://localhost:3000> |

> [!WARNING]
> 数据库迁移会创建本地验收账号 `admin`、`editor` 和 `viewer`，默认密码均为 `password123`。它们只用于本地 Demo；不要使用默认密钥或默认账号把服务暴露到公网。

### 4. 打开 Demo

访问 <http://localhost:8080>，使用 `admin` 登录，然后按下面的顺序体验完整链路：

1. 在「模型设置」检查 LLM 与 Ollama 连接；
2. 创建 Source KB 并上传 `.md` 或 `.txt`；
3. 创建 Wiki KB、绑定 Source KB，再手动执行「生成/更新」；
4. 在 Wiki 浏览器、知识图谱和问答对话中检查结果与来源。

## 项目状态与边界

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| M0–M3 | 已完成 | 工程基线、账号与 KB、文档摄入、Wiki 生成／浏览／图谱 |
| M4 | 进行中 | Micro Eval 已接入；Scenario Eval runner、对应的真实质量报告与生成质量修复仍在推进 |
| M5 | 已完成 | 单 KB 会话、混合检索、流式回答、引用详情、QA runner 与 Docker 集成走查 |
| M6–M7 | 未开始 | Wiki 编辑／版本／审计查询，以及由真实需求触发的检索和多 KB 演进 |

当前明确边界：

- 只接收 `.md` 与 `.txt`，默认单文件不超过 10 MB；
- 只开放一个「当前团队」，不提供多 Workspace 切换；
- 问答会话一次只绑定一个物理 KB，不做多 KB 联合检索；
- v1 只接受 Ollama 1024 维 Embedding 模型；
- Wiki ingest 需要手动触发，Wiki 编辑、版本 Diff、回滚和审计查询界面尚未完成；
- Wiki 与回答仍可能出现生成质量问题，应结合来源定位、固定语料评估和 Trace 验证。

完整进度与后置范围以 [v1 开发路线图](docs/v1/ROADMAP.md) 为准；缺陷与质量跟踪见 [GitHub Issues](https://github.com/Quashy/OpenWiki/issues)。

## 技术栈

| 层次 | 主要组件 |
| --- | --- |
| Web | React 18、Vite 6、TypeScript、Tailwind CSS 4、HeroUI、TanStack Query、Zustand、ECharts |
| API / Worker | FastAPI、SQLAlchemy 2.0 async、Alembic、Redis、ARQ |
| 数据与检索 | PostgreSQL 16、pgvector、pg_bigm、Ollama Embedding |
| LLM 与观测 | OpenAI / DeepSeek 兼容接口、Langfuse |

<details>
<summary><strong>查看运行架构</strong></summary>

```mermaid
flowchart TB
    browser[React SPA] -->|HTTP / SSE| api[FastAPI API]
    api --> db[(PostgreSQL<br/>pgvector + pg_bigm)]
    api --> redis[(Redis)]
    api --> ollama[Ollama Embedding]
    api --> llm[OpenAI / DeepSeek<br/>compatible LLM]
    redis --> worker[ARQ Worker]
    worker --> db
    worker --> ollama
    worker --> llm
    api -. trace .-> langfuse[Langfuse]
    worker -. trace .-> langfuse
```

</details>

<details>
<summary><strong>查看本地源码开发与验证命令</strong></summary>

源码开发需要 Node.js 22+、Python 3.12+，并先启动 PostgreSQL 与 Redis：

```powershell
docker compose up -d db redis

$env:DATABASE_URL="postgresql+asyncpg://openwiki:openwiki@localhost:5432/openwiki"
$env:REDIS_URL="redis://localhost:6379/0"
$env:OLLAMA_BASE_URL="http://localhost:11434"

cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

另开一个终端，重复设置上面的 `DATABASE_URL`、`REDIS_URL` 与 `OLLAMA_BASE_URL`，再启动 Worker：

```powershell
cd backend
.\.venv\Scripts\arq app.workers.main.WorkerSettings
```

再开一个终端启动前端：

```powershell
npm --prefix frontend ci
npm run frontend:dev
```

交付前检查：

```powershell
npm ci
npm run api:lint
npm run frontend:lint
npm run frontend:build

cd backend
.\.venv\Scripts\python -m pytest
```

</details>

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [v1 ROADMAP](docs/v1/ROADMAP.md) | 里程碑、完成证据、范围裁剪与后置项 |
| [产品需求](docs/PRD-LLM-Wiki知识库系统.md) | 产品定位、角色、用户流程与功能范围 |
| [技术设计](docs/TRD-LLM-Wiki知识库系统.md) | 数据模型、服务设计、任务与检索细节 |
| [架构说明](docs/architecture.md) | 系统组件、核心链路、部署与可观测性 |
| [OpenAPI 契约](docs/api/openapi.yaml) | `/api/v1` 主契约；同时包含后续里程碑规划接口 |
| [API 说明](docs/api/API.md) | 当前接口口径、权限与关键负例 |
| [Wiki 质量评估](docs/evals/wiki/README.md) | 固定 Case、Scenario、运行方式与指标说明 |
| [Prompt 说明](docs/prompt/prompt.md) | Wiki Prompt 模板、阶段输入输出与版本约定 |

## 许可证

当前仓库尚未声明开源许可证。在补充 `LICENSE` 前，请不要假定代码已经获得开放使用、修改或分发授权。
