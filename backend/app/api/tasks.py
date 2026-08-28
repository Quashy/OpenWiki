from fastapi import APIRouter

from app.deps import CurrentPrincipalDep, SessionDep
from app.schemas import TaskOut
from app.services.task_service import get_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskOut)
async def get_task_status(
    task_id: str,
    principal: CurrentPrincipalDep,
    session: SessionDep,
) -> TaskOut:
    return await get_task(session, workspace_id=principal.workspace.id, task_id=task_id)
