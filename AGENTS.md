# OpenWiki V2 智能体协作指南

## 语言

始终使用简体中文回复用户。

## 项目事实源

开始里程碑开发前，先阅读以下文档：

1. `docs/v1/ROADMAP.md`
2. `docs/api/openapi.yaml`
3. `docs/api/API.md`
4. `docs/TRD-LLM-Wiki知识库系统.md`
5. `docs/architecture.md`
6. `docs/PRD-LLM-Wiki知识库系统.md`

`docs/api/openapi.yaml` 是接口主契约。后端响应、前端 API 类型和 mock 数据都必须与它一致；契约一致性靠 Redocly lint 全局保障，不逐接口编写契约测试。

## 当前开发方式

按里程碑推进。

需求冲突时，按以下优先级判断：

1. ROADMAP
2. OpenAPI 契约
3. API 说明
4. TRD
5. Architecture
6. PRD
7. Prototype

## 前后端分工

前端智能体主要修改 `frontend/`。

后端智能体主要修改 `backend/`、`docker/`、数据库迁移和后端测试。

双方都可以读取全部文档。接口需要变化时，先更新 `docs/api/openapi.yaml`，再改实现。

避免两个智能体同时编辑同一个文件。如果文件已有用户或其他智能体的改动，先阅读并基于现有改动继续工作。

## API 契约规则

每个业务接口都应具备：

- 必要的请求 schema。
- 必要的成功响应 schema。
- 统一的 `ErrorResponse` 错误结构。
- 与 OpenAPI 一致的前端 API 调用和类型结构。

认证、Workspace 隔离和 RBAC 由共享依赖统一实现，在代表性接口上集中测试一次，不按接口重复写权限矩阵测试。

v1 问答不要重新引入 `kb_ids`。Chat session 只绑定一个物理 `kb_id`。

v1 不添加多 Workspace 创建、列表或切换接口。

## 后端规范

使用 FastAPI async API、SQLAlchemy 2.0 async、Alembic、Redis/ARQ，以及 PostgreSQL 16 + `pgvector` + `pg_bigm`。

服务边界保持与 TRD 目录结构一致。只有当前里程碑确实需要时，才新增真实抽象。

所有写操作最终都必须包含 RBAC、审计日志和事务边界。测试策略：后端只保留两类 pytest 测试——横切关注点冒烟（认证/RBAC/审计各覆盖一次）与固定语料管线测试（分块、召回、Wiki 后处理）；前端不编写测试。

长任务必须通过 `task_pending_ops` 追踪；公共 API 通过 `GET /tasks/{task_id}` 暴露任务状态。

## 前端规范

使用 React 18、Vite、TypeScript、Tailwind CSS v4、HeroUI、React Query、Zustand、ECharts 和 lucide-react。

交互基础组件默认使用 HeroUI：按钮、输入框、选择器、弹窗、表格、标签页、下拉菜单、开关和 toast。

Tailwind 用于页面布局和产品特定组合。界面应保持信息密度适中、克制、偏内部工具风格；不要做成营销落地页。

后端未完成时，前端可以使用本地 mock，但 mock 数据必须匹配 `docs/api/openapi.yaml`。

## 质量门禁

采用分层门禁，兼顾敏捷开发和交付质量。不要在每次小改动后机械跑全量检查；先跑与改动直接相关的最快检查，里程碑收尾或交付前再跑全量。

日常内循环：

- 改前端组件或前端逻辑：以页面手动验证为主；改动依赖、构建配置或路由入口时跑生产构建。
- 改后端单模块：优先跑相关 `pytest` 测试。
- 改文档或固定语料：通常只做内容自查；除非影响契约或命令说明，不跑前后端全量。
- 没改 OpenAPI，不跑 Redocly lint。
- 没改 Docker、Compose 或端口配置，不跑 `docker compose config`。
- 没改数据库迁移，不跑 Alembic 迁移验证。
- 没改前端依赖、构建配置或路由入口，不必每次跑生产构建。

交付前或里程碑收尾必须运行相关全量检查：

- 后端：`pytest`。
- 前端：生产构建。
- API 契约变更：对 `docs/api/openapi.yaml` 执行 Redocly lint。
- Docker 变更：执行 `docker compose config`。
- 数据库迁移变更：执行 Alembic 迁移验证。

如果某项检查无法运行，说明具体原因和剩余风险。

## Git 与安全

除非用户明确要求，不要创建 commit、branch，不要执行 reset、rebase 或 push。

删除文件、大范围重写、破坏性命令执行前，必须获得用户明确确认。

优先做小而清晰的里程碑内改动。遵循 KISS、YAGNI、DRY、SOLID，但不要在代码真正需要前提前抽象。
