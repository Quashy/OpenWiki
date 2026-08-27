# OpenWiki V2

企业内部 LLM Wiki 知识库系统。当前工程初始化目标对齐 `docs/v1/ROADMAP.md` 的 M0。

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

OpenAPI 契约校验：

```powershell
npm install
npm run api:lint
```

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

如果本机端口已被占用，可在 `.env` 中调整 `POSTGRES_PORT`、`REDIS_PORT`、`LANGFUSE_PORT`、`BACKEND_PORT` 或 `FRONTEND_PORT`。

服务端口：

- Frontend: http://localhost:8080
- Backend: http://localhost:8000/api/v1/health
- Backend Docs: http://localhost:8000/api/v1/docs
- Langfuse: http://localhost:3000

## 质量命令

```powershell
cd backend
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy app tests
.\.venv\Scripts\python -m pytest

cd ..\frontend
npm run lint
npm run test
npm run build
```

数据库迁移：

```powershell
cd backend
.\.venv\Scripts\alembic upgrade head
```

从宿主机连接 Docker 数据库执行迁移时，使用本机端口地址：

```powershell
cd backend
$env:DATABASE_URL="postgresql+asyncpg://openwiki:openwiki@localhost:5432/openwiki"
.\.venv\Scripts\alembic upgrade head
```

固定质量语料位于 `docs/v1/quality-corpus/`，供 M2-M6 的分块、检索、Wiki ingest 和问答验收复用。
