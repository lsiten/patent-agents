from fastapi import APIRouter

from src.api.runtime_state import tasks_store, workflow_lock
from src.models.enums import WorkflowState

router = APIRouter(tags=["dashboard"])


@router.get("/stats/dashboard")
async def get_dashboard_stats():
    """获取仪表盘统计数据。"""
    async with workflow_lock:
        tasks = list(tasks_store.values())

    return {
        "total_tasks": len(tasks),
        "completed_tasks": sum(1 for task in tasks if task.current_state == WorkflowState.COMPLETED),
        "in_progress_tasks": sum(
            1
            for task in tasks
            if task.current_state not in [WorkflowState.COMPLETED, WorkflowState.FAILED]
        ),
        "failed_tasks": sum(1 for task in tasks if task.current_state == WorkflowState.FAILED),
        "active_agents": 5,
        "avg_completion_time": "2.5 hours",
        "success_rate": 94.5,
    }
