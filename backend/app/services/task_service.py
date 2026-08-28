from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import KnowledgeBase, TaskPendingOp
from app.models.m1 import now_utc
from app.schemas import TaskOut


def task_out(task: TaskPendingOp) -> TaskOut:
    return TaskOut.model_validate(task)


async def get_task(
    session: AsyncSession,
    *,
    workspace_id: str,
    task_id: str,
) -> TaskOut:
    task = await session.scalar(
        select(TaskPendingOp)
        .join(KnowledgeBase, KnowledgeBase.id == TaskPendingOp.kb_id)
        .where(
            TaskPendingOp.id == task_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if task is None:
        raise ApiError("not_found", "任务不存在", 404)
    return task_out(task)


async def update_task(
    session: AsyncSession,
    task: TaskPendingOp,
    *,
    status: str,
    stage: str,
    progress: int,
    error: dict[str, object] | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    task.status = status
    task.stage = stage
    task.progress = progress
    task.error = error
    if payload is not None:
        task.payload = payload
    task.updated_at = now_utc()
    await session.commit()
