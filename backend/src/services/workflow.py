"""
工作流编排服务
封装 PatentWorkflowEngine 的工作流生命周期管理
"""
from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from src.core.workflow_engine import (
    PatentWorkflowEngine,
    WorkflowContext,
    WorkflowState,
    PhaseResult,
)


class WorkflowService:
    """工作流编排服务"""

    def __init__(
        self,
        workflow_engine: PatentWorkflowEngine,
        event_bus=None,
    ) -> None:
        self._engine = workflow_engine
        self._event_bus = event_bus
        self._events: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = Lock()

    # ── 工作流生命周期 ─────────────────────────────────────

    def create_workflow(
        self,
        task_id: str,
        user_id: str,
        description: str,
        patent_type_preference: str | None = None,
    ) -> WorkflowContext:
        """创建新的工作流会话"""
        context = self._engine.create_workflow(
            task_id=task_id,
            user_id=user_id,
            description=description,
            patent_type_preference=patent_type_preference,
        )
        self._append_event(
            task_id, "workflow_engine", "专利工作流会话已创建，进入头脑风暴阶段",
            "workflow.created",
            {"state": context.current_phase.value},
        )
        return context

    def get_workflow(self, task_id: str) -> WorkflowContext | None:
        """获取工作流上下文"""
        return self._engine.get_workflow(task_id)

    def list_workflows(self) -> List[WorkflowContext]:
        """列出所有工作流"""
        return self._engine.list_workflows()

    def cancel_workflow(self, task_id: str) -> bool:
        """取消工作流"""
        result = self._engine.cancel_workflow(task_id)
        if result:
            self._append_event(
                task_id, "workflow_engine", "工作流已取消", "workflow.cancelled"
            )
        return result

    # ── 对话交互 ──────────────────────────────────────────

    async def add_chat_message(
        self,
        task_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """向工作流添加聊天消息"""
        try:
            response = await self._engine.add_chat_message(
                task_id=task_id,
                role=role,
                content=content,
            )
            with self._lock:
                self._events.setdefault(task_id, [])
            logger.debug(
                "工作流聊天消息已处理",
                task_id=task_id,
                role=role,
            )
            return response
        except ValueError as e:
            logger.error("工作流聊天失败", task_id=task_id, error=str(e))
            raise

    def get_messages(self, task_id: str) -> List[Dict[str, Any]]:
        """获取工作流对话历史"""
        context = self._engine.get_workflow(task_id)
        if not context:
            return []
        return context.message_history

    # ── 工作流执行 ─────────────────────────────────────────

    async def start_workflow(
        self,
        task_id: str,
        phase_callback: Callable | None = None,
    ) -> None:
        """启动完整工作流（异步）"""
        context = self._engine.get_workflow(task_id)
        if not context:
            raise ValueError(f"工作流不存在: {task_id}")

        self._append_event(
            task_id, "workflow_engine", "专利申请流程已启动", "workflow.started"
        )

        try:
            await self._engine.execute_full_workflow(
                context,
                phase_callback=phase_callback or self._default_phase_callback(task_id),
            )
            self._append_event(
                task_id, "workflow_engine", "专利申请流程已完成",
                "workflow.completed",
                {"state": context.current_phase.value},
            )
        except asyncio.CancelledError:
            self._append_event(
                task_id, "workflow_engine", "工作流已被取消",
                "workflow.cancelled",
            )
        except Exception as e:
            self._append_event(
                task_id, "workflow_engine", str(e),
                "workflow.failed",
            )
            raise

    # ── 事件流 ────────────────────────────────────────────

    def get_events(self, task_id: str) -> List[Dict[str, Any]]:
        """获取工作流事件列表"""
        return list(self._events.get(task_id, []))

    # ── 内部辅助 ──────────────────────────────────────────

    def _append_event(
        self,
        task_id: str,
        agent: str,
        message: str,
        event_type: str,
        data: Dict[str, Any] | None = None,
    ) -> None:
        from datetime import datetime

        with self._lock:
            self._events.setdefault(task_id, []).append({
                "task_id": task_id,
                "timestamp": datetime.now(),
                "agent": agent,
                "message": message,
                "event_type": event_type,
                "data": data or {},
            })

    def _default_phase_callback(self, task_id: str) -> Callable:
        """创建默认的阶段回调"""
        async def callback(phase: WorkflowState, result: PhaseResult) -> None:
            self._append_event(
                task_id,
                phase.value,
                f"阶段 {phase.value} 已完成",
                "workflow.phase.completed",
                {
                    "phase": phase.value,
                    "success": result.success,
                    "duration_seconds": result.duration_seconds,
                    "issues": result.issues,
                },
            )
        return callback
