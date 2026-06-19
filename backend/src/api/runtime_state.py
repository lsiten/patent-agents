# -*- coding: utf-8 -*-
"""In-process API runtime state.

This is the current development runtime backing the thin FastAPI route layer.
It keeps global state out of ``routes.py`` while preserving the existing API
surface. Production deployments can replace these objects with durable stores.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from loguru import logger

from ..core.workflow import PatentWorkflowEngine
from ..models.domain import PatentTask
from .schemas import OrgNodeResponse, WorkflowEventResponse

tasks_store: Dict[str, PatentTask] = {}
task_events: Dict[str, List[WorkflowEventResponse]] = {}
workflow_lock = asyncio.Lock()
workflow_background_tasks: Dict[str, asyncio.Task[Any]] = {}

conversations_store: Dict[str, dict] = {}
conversations_lock = asyncio.Lock()
CONVERSATION_STREAM_HEARTBEAT_SECONDS = 15.0
conversation_event_queues: Dict[str, List[Dict[str, Any]]] = {}
conversation_stream_finalization_tasks: set[asyncio.Task[Any]] = set()

workflow_engine = PatentWorkflowEngine()
organization_tree_store: OrgNodeResponse | None = None


def track_workflow_background_task(task_id: str, coro: Any) -> asyncio.Task[Any]:
    """Track workflow coroutines so cancellation can stop real background work."""
    existing = workflow_background_tasks.get(task_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(coro)
    workflow_background_tasks[task_id] = task

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        if workflow_background_tasks.get(task_id) is done_task:
            workflow_background_tasks.pop(task_id, None)
        if done_task.cancelled():
            return
        try:
            exc = done_task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.exception("Workflow background task failed", task_id=task_id, error=exc)

    task.add_done_callback(_cleanup)
    return task


def cancel_workflow_background_task(task_id: str) -> bool:
    """Cancel an in-process workflow task if it is still running."""
    task = workflow_background_tasks.pop(task_id, None)
    if not task or task.done():
        return False
    task.cancel()
    return True


def workflow_background_task_running(task_id: str) -> bool:
    """Return whether a workflow has an active background task."""
    task = workflow_background_tasks.get(task_id)
    return bool(task and not task.done())
