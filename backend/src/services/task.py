"""
专利申请任务管理服务
管理专利任务的全生命周期，包括创建、执行、事件流
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from src.models.domain import PatentTask
from src.models.enums import WorkflowState
from src.repositories.unit_of_work import UnitOfWork


class TaskService:
    """专利任务管理服务"""

    def __init__(
        self,
        uow_factory,
        ceo_agent_factory=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._ceo_agent_factory = ceo_agent_factory

        # 内存存储 — 后续迁移到 DB
        self._tasks: Dict[str, PatentTask] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        user_id: str,
        tech_description: str,
        patent_type_preference: Optional[str] = None,
        title: Optional[str] = None,
    ) -> PatentTask:
        """创建新的专利申请任务"""
        task_id = str(uuid4())

        task = PatentTask(
            task_id=task_id,
            user_id=user_id,
            tech_description=tech_description,
            patent_type_preference=patent_type_preference,
            title=title,
            current_state=WorkflowState.INITIAL,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            iteration_count=0,
            max_iterations=3,
        )

        async with self._lock:
            self._tasks[task_id] = task
            self._events[task_id] = self._append_event(
                task_id, "system", "任务已创建", "task.created"
            )

        logger.info("专利申请任务创建成功", task_id=task_id, user_id=user_id)
        return task

    async def get_task(self, task_id: str) -> Optional[PatentTask]:
        """获取任务"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(
        self,
        user_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> List[PatentTask]:
        """列出任务"""
        async with self._lock:
            tasks = list(self._tasks.values())

        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]

        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset : offset + limit]

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.current_state in (WorkflowState.COMPLETED, WorkflowState.FAILED):
                return False

            task.current_state = WorkflowState.FAILED
            task.error_message = "用户取消任务"
            task.updated_at = datetime.now()

            self._events.setdefault(task_id, []).append(
                self._append_event(
                    task_id, "system", "任务已被用户取消", "task.cancelled"
                )
            )

            logger.info("任务已取消", task_id=task_id)
            return True

    async def get_task_events(
        self, task_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """获取任务事件"""
        async with self._lock:
            events = self._events.get(task_id)
            if events is None:
                return None
            return list(events)

    async def stream_task_events(
        self, task_id: str
    ) -> AsyncGenerator[str, None]:
        """SSE 事件流生成器"""
        while True:
            async with self._lock:
                events = list(self._events.get(task_id, []))
                task = self._tasks.get(task_id)

            yield events

            if task and task.current_state in (
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
            ):
                break

            await asyncio.sleep(1)

    async def append_task_event(
        self,
        task_id: str,
        agent: str,
        message: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """追加任务事件（供工作流引擎回调使用）"""
        async with self._lock:
            self._events.setdefault(task_id, []).append(
                self._append_event(task_id, agent, message, event_type, data)
            )

    async def get_task_stats(self) -> Dict[str, Any]:
        """获取任务统计（仪表盘用）"""
        async with self._lock:
            tasks = list(self._tasks.values())

        completed = sum(1 for t in tasks if t.current_state == WorkflowState.COMPLETED)
        failed = sum(1 for t in tasks if t.current_state == WorkflowState.FAILED)
        in_progress = sum(
            1
            for t in tasks
            if t.current_state not in (WorkflowState.COMPLETED, WorkflowState.FAILED)
        )

        return {
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "failed_tasks": failed,
        }

    # ── 内部辅助 ──────────────────────────────────────────

    def _append_event(
        self,
        task_id: str,
        agent: str,
        message: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "timestamp": datetime.now(),
            "agent": agent,
            "message": message,
            "event_type": event_type,
            "data": data or {},
        }
