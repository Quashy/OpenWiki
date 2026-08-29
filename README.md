# OpenWiki V2

OpenWiki V2 是一个面向团队内部知识沉淀的 LLM Wiki 知识库系统。它把原始 Markdown/TXT 文档摄入为 Source KB，再通过多阶段 LLM 流水线生成结构化、可互链、可溯源的 Wiki KB，并提供 Wiki 浏览器、知识图谱和后续 RAG 问答入口。

当前项目处于 v1 demo 主线开发中：M0-M3 已完成，M4 正在收口 Wiki Prompt 质量，下一阶段是 M5 单 KB RAG 问答。

## 功能状态

| 能力 | 状态 |
|---|---|
| 注册、登录、当前团队、成员角色与 RBAC | 已完成 |
| LLM 配置、Ollama embedding 配置与模型探测 | 已完成 |
| Source KB / Wiki KB 创建与绑定 | 已完成 |
| Markdown/TXT 上传、标签、去重、分块、向量化 | 已完成 |
| Wiki ingest / rebuild 六阶段流水线 | 已完成 |
| Wiki 页面浏览、Markdown 渲染、双链跳转、来源定位 | 已完成 |
| 知识图谱数据接口与 ECharts 交互视图 | 已完成 |
| Wiki Prompt eval、Micro Eval、Dedup、prompt version trace | 进行中 |
| 单 KB RAG 问答、SSE 流式输出、回答引用 | 未开始 |
| Wiki 编辑、版本 diff、回滚、审计查询 | demo 后补齐 |

详细里程碑见 [docs/v1/ROADMAP.md](docs/v1/ROADMAP.md)。

## 系统架构

```text
React + Vite frontend
        |
        v
FastAPI API (/api/v1)
        |
        +--> PostgreSQL 16 + pgvector + pg_bigm
        +--> Redis + ARQ worker
        +--> Ollama embedding
        +--> OpenAI / DeepSeek-compatible chat completion
        +--> Langfuse tracing
```

核心数据流：

```text
Upload documents
  -> chunk and embed Source KB
  -> extract Wiki candidates
  -> deduplicate candidates
  -> attach citations
  -> plan taxonomy
  -> summarize source documents
  -> reduce entity/concept pages
  -> post-process links, graph and Wiki page embeddings
```

## 技术栈

后端：

- FastAPI
- SQLAlchemy 2.0 async
- Alembic
- PostgreSQL 16
- pgvector
- pg_bigm
- Redis / ARQ
- Langfuse
- OpenAI-compatible LLM provider
- Ollama embedding

前端：

- React 18
- Vite
- TypeScript
- Tailwind CSS v4
- HeroUI
- React Query
- Zustand
- ECharts
- lucide-react
- react-markdown / remark-gfm

## 快速开始

### 1. 准备依赖

需要本机具备：

- Docker Desktop
- Node.js 22+
- Python 3.12+
- Ollama

v1 默认使用 Ollama 的 1024 维 embedding 模型。推荐先准备 `bge-m3`：

```powershell
ollama pull bge-m3
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

至少检查这些配置：

```dotenv
JWT_SECRET=change-me-in-production
ENCRYPTION_KEY=base64-encoded-32-byte-key
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_EMBED_MODEL=bge-m3
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
```

Wiki 生成需要配置一个可用的 LLM Key。系统支持 OpenAI-compatible chat completion，当前实现优先覆盖 OpenAI / DeepSeek 兼容接口。

### 3. 启动服务

```powershell
docker compose up --build
```

服务地址：

| 服务 | 地址 |
|---|---|
| Web UI | http://localhost:8080 |
| API health | http://localhost:8000/api/v1/health |
| Swagger UI | http://localhost:8000/api/v1/docs |
| Langfuse | http://localhost:3000 |

第一次注册的用户会创建当前团队并成为 Admin。后续注册用户需要由 Admin 加入团队后才能访问团队资源。

## 本地开发

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

根目录常用命令：

```powershell
npm run api:lint
npm run frontend:lint
npm run frontend:build
```

后端测试：

```powershell
cd backend
.\.venv\Scripts\python -m pytest
```

数据库迁移：

```powershell
cd backend
.\.venv\Scripts\alembic upgrade head
```

如果从宿主机连接 Docker 数据库执行迁移，使用本机端口地址：

```powershell
cd backend
$env:DATABASE_URL="postgresql+asyncpg://openwiki:openwiki@localhost:5432/openwiki"
.\.venv\Scripts\alembic upgrade head
```

## API

API 前缀为 `/api/v1`。OpenAPI 是接口主契约：

- [docs/api/openapi.yaml](docs/api/openapi.yaml)
- [docs/api/API.md](docs/api/API.md)

主要接口分组：

- Auth：注册、登录、刷新 token、退出登录
- Workspace / Members：当前团队与成员管理
- Admin：LLM 配置、Ollama 配置、模型探测
- Knowledge Bases：Source KB / Wiki KB 创建、绑定、配置
- Documents / Tags：上传、列表、详情、删除、重试、标签
- Tasks：长任务状态查询
- Wiki：ingest、rebuild、页面列表、页面详情、来源定位、图谱

Chat API 已在契约中规划，M5 阶段实现。

## Wiki 质量评估

Wiki Prompt 质量评估语料位于：

- [docs/evals/wiki/](docs/evals/wiki/)
- [docs/prompt/](docs/prompt/)

当前 M4 重点：

- 固定 `wiki_prompt_v0.3` 作为 demo baseline
- 使用 Micro Eval 检查页面、别名、引用、关系、死链、自链和禁止内容
- 使用 Langfuse trace 记录 prompt family、stage、version
- 避免继续堆 prompt 文案导致过拟合

评估报告默认写入 `reports/`，该目录不进入 Git。

## 已知限制

- v1 只支持 `.md` 和 `.txt` 上传。
- v1 只支持单当前团队，不开放多 Workspace 创建或切换。
- v1 问答会话只绑定单个 `kb_id`，不支持多 KB 联合问答。
- v1 embedding 默认收敛到 Ollama 1024 维模型。
- Wiki 自动生成仍可能出现质量问题；当前优先用 eval 和确定性后处理收敛，而不是无限强化 prompt。
- 审计日志写入已随写接口推进，查询界面在 M6 补齐。

近期质量修复跟踪见 GitHub Issues：

- [#1 复现全量重建下的伪相关条目](https://github.com/Quashy/OpenWiki/issues/1)
- [#2 Reduce 空输出不再静默生成伪页面](https://github.com/Quashy/OpenWiki/issues/2)
- [#3 fallback 页面只展示当前页面自己的证据](https://github.com/Quashy/OpenWiki/issues/3)
- [#4 图谱关系必须有显式证据约束](https://github.com/Quashy/OpenWiki/issues/4)
- [#5 Reduce 输入链接收窄到证据邻域](https://github.com/Quashy/OpenWiki/issues/5)
- [#6 清理并验证历史伪关系数据](https://github.com/Quashy/OpenWiki/issues/6)

## 文档索引

| 文档 | 用途 |
|---|---|
| [docs/v1/ROADMAP.md](docs/v1/ROADMAP.md) | v1 里程碑、范围裁剪和验收门禁 |
| [docs/PRD-LLM-Wiki知识库系统.md](docs/PRD-LLM-Wiki知识库系统.md) | 产品需求 |
| [docs/TRD-LLM-Wiki知识库系统.md](docs/TRD-LLM-Wiki知识库系统.md) | 技术设计 |
| [docs/architecture.md](docs/architecture.md) | 架构说明 |
| [docs/api/openapi.yaml](docs/api/openapi.yaml) | API 主契约 |
| [docs/api/API.md](docs/api/API.md) | API 说明和关键负例 |
| [docs/evals/wiki/README.md](docs/evals/wiki/README.md) | Wiki 质量评估数据说明 |
| [docs/prompt/prompt.md](docs/prompt/prompt.md) | Wiki prompt 模板 |

## 开发约定

- 以 [docs/v1/ROADMAP.md](docs/v1/ROADMAP.md) 为当前阶段事实源。
- API 变更先改 [docs/api/openapi.yaml](docs/api/openapi.yaml)，再改后端和前端。
- 日常开发优先运行与改动相关的最快检查；里程碑收尾再跑全量检查。
- 不把 `reports/`、`.scratch/`、`uploads/` 中的本地运行产物提交进 Git。
- 写操作必须包含 RBAC、审计日志和清晰事务边界。

## 许可证

当前仓库尚未声明开源许可证。对外公开或接受外部贡献前，需要先补充 `LICENSE`。
