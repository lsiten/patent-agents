from typing import Dict, List, Callable, Optional
from datetime import datetime

from loguru import logger

from ..models.enums import WorkflowState


class WorkflowStateMachine:
    """工作流状态机"""

    def __init__(self):
        # 状态转换图: {当前状态: {允许的下一状态列表}}
        self.transitions: Dict[WorkflowState, List[WorkflowState]] = {
            WorkflowState.INITIAL: [
                WorkflowState.REQUIREMENT_ANALYSIS,
                WorkflowState.FAILED,
            ],
            WorkflowState.REQUIREMENT_ANALYSIS: [
                WorkflowState.RETRIEVAL_ANALYSIS,
                WorkflowState.INITIAL,  # 返回补充信息
                WorkflowState.FAILED,
            ],
            WorkflowState.RETRIEVAL_ANALYSIS: [
                WorkflowState.WRITING,
                WorkflowState.FAILED,
            ],
            WorkflowState.WRITING: [
                WorkflowState.REVIEWING,
                WorkflowState.FAILED,
            ],
            WorkflowState.REVIEWING: [
                WorkflowState.ITERATION,
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
            ],
            WorkflowState.ITERATION: [
                WorkflowState.REVIEWING,
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
            ],
            WorkflowState.COMPLETED: [],  # 终态
            WorkflowState.FAILED: [],     # 终态
        }

        # 状态回调
        self._on_enter_callbacks: Dict[WorkflowState, List[Callable]] = {}
        self._on_exit_callbacks: Dict[WorkflowState, List[Callable]] = {}

    def can_transition(self, from_state: WorkflowState, to_state: WorkflowState) -> bool:
        """检查是否允许状态转换"""
        allowed_states = self.transitions.get(from_state, [])
        return to_state in allowed_states

    def transition(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
        context: Optional[Dict] = None,
    ) -> bool:
        """执行状态转换"""
        if not self.can_transition(from_state, to_state):
            logger.warning(
                f"非法状态转换: {from_state} -> {to_state}, "
                f"允许的转换: {self.transitions.get(from_state, [])}"
            )
            return False

        # 执行退出回调
        self._execute_callbacks(self._on_exit_callbacks, from_state, context)

        # 执行进入回调
        self._execute_callbacks(self._on_enter_callbacks, to_state, context)

        logger.info(f"状态转换: {from_state} -> {to_state}")
        return True

    def on_enter(self, state: WorkflowState, callback: Callable):
        """注册进入状态的回调"""
        if state not in self._on_enter_callbacks:
            self._on_enter_callbacks[state] = []
        self._on_enter_callbacks[state].append(callback)

    def on_exit(self, state: WorkflowState, callback: Callable):
        """注册退出状态的回调"""
        if state not in self._on_exit_callbacks:
            self._on_exit_callbacks[state] = []
        self._on_exit_callbacks[state].append(callback)

    def _execute_callbacks(self, callback_map: Dict, state: WorkflowState, context: Optional[Dict]):
        """执行回调"""
        callbacks = callback_map.get(state, [])
        for callback in callbacks:
            try:
                callback(state, context)
            except Exception as e:
                logger.error(f"状态回调执行失败: {e}")

    def get_next_states(self, current_state: WorkflowState) -> List[WorkflowState]:
        """获取允许的下一状态列表"""
        return self.transitions.get(current_state, [])

    def is_terminal_state(self, state: WorkflowState) -> bool:
        """检查是否为终态"""
        return state in [WorkflowState.COMPLETED, WorkflowState.FAILED]


class WorkflowProgress:
    """工作流进度追踪器"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.start_time = datetime.now()
        self.state_history: List[Dict] = []

    def record_state_change(self, from_state: WorkflowState, to_state: WorkflowState, metadata: Optional[Dict] = None):
        """记录状态变化"""
        self.state_history.append({
            "from": from_state,
            "to": to_state,
            "timestamp": datetime.now(),
            "metadata": metadata or {},
        })

    def get_elapsed_time(self) -> float:
        """获取执行时间（秒）"""
        return (datetime.now() - self.start_time).total_seconds()

    def get_current_state(self) -> Optional[WorkflowState]:
        """获取当前状态"""
        if self.state_history:
            return self.state_history[-1]["to"]
        return None

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "task_id": self.task_id,
            "start_time": self.start_time.isoformat(),
            "elapsed_seconds": self.get_elapsed_time(),
            "state_history": [
                {
                    "from": h["from"],
                    "to": h["to"],
                    "timestamp": h["timestamp"].isoformat(),
                }
                for h in self.state_history
            ],
        }


# 单例状态机实例
_state_machine: Optional[WorkflowStateMachine] = None


def get_state_machine() -> WorkflowStateMachine:
    """获取状态机单例"""
    global _state_machine
    if _state_machine is None:
        _state_machine = WorkflowStateMachine()
    return _state_machine
