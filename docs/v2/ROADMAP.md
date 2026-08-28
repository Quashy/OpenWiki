# OpenWiki V2 v2 演进路线图

> 日期：2026-08-28
> 状态：规划草案
> 关联背景：v1 M3 Wiki 全量重建真实 DeepSeek 运行暴露 ARQ 默认超时与单队列并发治理问题。

## 1. 背景

v1 M3 已完成 Wiki ingest 主链路。一次测试 Wiki 库全量更新中，任务在 `reducing` 阶段被 ARQ 默认 `job_timeout=300s` 取消；由于 `asyncio.CancelledError` 没有被普通 `except Exception` 捕获，历史任务残留为 `running`，对应 Wiki KB 残留为 `building`。

已在 v1 代码中补齐两个止血措施：

- 显式处理 worker 取消，任务失败时恢复 KB 为 `active`，避免长期卡住。
- 将 worker 运行参数移入 `backend/config/worker.toml`，当前默认 `job_timeout_seconds=1800`、`max_jobs=4`。

当前 `max_jobs` 的语义是单个 ARQ worker 的总并发上限。文档处理、Wiki ingest、Wiki rebuild 和 debounce ingest 共用同一个队列与 worker 配置，因此它不是 Wiki 专属并发。

## 2. V2 目标

V2 需要把后台任务从单队列演进为分池治理，目标是隔离资源、降低互相挤占，并让不同任务类型拥有独立超时与并发预算。

优先拆分的 worker pool：

| Pool | 职责 | 初始并发建议 | 说明 |
|---|---|---:|---|
| document | 文档解析、分块、基础入库 | 4 | 受文件大小、CPU 与数据库写入影响 |
| wiki | Wiki ingest / rebuild 六阶段生成 | 4-8 | 受 LLM 限流、token 量、引用归并耗时影响 |
| enrichment | 后续摘要、图谱增强、推荐问题等增强任务 | 4-8 | 可降级、可延迟，不应阻塞核心链路 |
| maintenance | stale task 回收、清理、补偿任务 | 1-2 | 低频后台维护 |
| shared | 轻量通用任务 | 2-4 | 仅承载无法明确归类的短任务 |

## 3. 设计要求

- 每个 pool 拥有独立队列名、函数列表、`job_timeout_seconds`、`max_jobs`、重试策略和健康检查。
- Wiki 全量更新不得挤占文档上传后的处理任务。
- 文档处理失败、Wiki 生成失败和 worker 取消必须统一落到 `task_pending_ops`，不得留下永久 `running/building` 状态。
- `task_pending_ops` 需要支持 stale task 回收：超过阈值仍无心跳的 `running` 任务应转为可重试失败态。
- 配置文件继续作为默认事实源；环境变量只作为部署覆盖层，不应替代结构化配置。

## 4. 后续里程碑建议

1. 引入多队列 enqueue：不同任务按职责投递到 `arq:document`、`arq:wiki` 等队列。
2. 扩展 worker 配置 loader：按 pool 启动不同 `WorkerSettings`。
3. 为 docker compose 增加多 worker 服务实例，并按 pool 注入启动目标。
4. 增加 stale task recovery 周期任务。
5. 基于 Langfuse 与结构化日志记录各 pool 的耗时、失败率、取消率和队列积压。
