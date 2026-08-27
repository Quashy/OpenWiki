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

服务端口：

- Frontend: http://localhost:8080
- Backend: http://localhost:8000/api/v1/health
- Backend Docs: http://localhost:8000/api/v1/docs
- Langfuse: http://localhost:3000

## 质量命令

```powershell
cd backend
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m pytest

cd ..\frontend
npm run lint
npm run test
npm run build
```

