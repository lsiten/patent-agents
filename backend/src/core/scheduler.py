"""
Agent Timer Scheduler — 基于 APScheduler 的 Agent 定时任务调度器
支持从持久化存储加载定时器，动态增删改查
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)

# 定时器数据存储路径
TIMERS_FILE = Path(__file__).parent.parent / "data" / "agent_timers.json"


class AgentTimerEntry:
    """定时器条目"""

    def __init__(
        self,
        id: str,
        agent_id: str,
        name: str,
        cron_expression: str,
        action: str,
        enabled: bool = True,
        action_type: str = "agent_run",
        action_config: Optional[Dict[str, Any]] = None,
        last_run_at: Optional[str] = None,
        next_run_at: Optional[str] = None,
        run_count: int = 0,
        last_run_status: Optional[str] = None,
        last_run_error: Optional[str] = None,
    ):
        self.id = id
        self.agent_id = agent_id
        self.name = name
        self.cron_expression = cron_expression
        self.action = action
        self.enabled = enabled
        self.action_type = action_type
        self.action_config = action_config or {}
        self.last_run_at = last_run_at
        self.next_run_at = next_run_at
        self.run_count = run_count
        self.last_run_status = last_run_status
        self.last_run_error = last_run_error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "cron_expression": self.cron_expression,
            "action": self.action,
            "enabled": self.enabled,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "run_count": self.run_count,
            "last_run_status": self.last_run_status,
            "last_run_error": self.last_run_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTimerEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})


def _parse_cron(expr: str) -> Dict[str, str]:
    """解析 5 字段 cron 表达式为 APScheduler 参数"""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expr} (expected 5 fields)")
    fields = ["minute", "hour", "day", "month", "day_of_week"]
    result = {}
    for field_name, value in zip(fields, parts):
        if value != "*":
            result[field_name] = value
    return result


class AgentScheduler:
    """
    Agent 定时任务调度器
    管理所有 Agent 的定时器，支持动态增删改
    """

    def __init__(self):
        self._timers: Dict[str, AgentTimerEntry] = {}
        self._jobs: Dict[str, Any] = {}  # timer_id -> scheduled job handle
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._action_handler: Optional[Callable] = None

    def set_action_handler(self, handler: Callable) -> None:
        """设置定时器触发时的动作处理器"""
        self._action_handler = handler

    def load_timers(self) -> None:
        """从文件加载所有定时器"""
        if not TIMERS_FILE.exists():
            logger.info("No timers file found, starting with empty timers")
            return

        try:
            with open(TIMERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for timer_data in data:
                timer = AgentTimerEntry.from_dict(timer_data)
                self._timers[timer.id] = timer
            logger.info("Loaded timers from file", count=len(self._timers))
        except Exception as e:
            logger.error("Failed to load timers", error=str(e))

    def save_timers(self) -> None:
        """持久化所有定时器到文件"""
        TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [timer.to_dict() for timer in self._timers.values()]
        with open(TIMERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Saved timers to file", count=len(data))

    def get_timers_for_agent(self, agent_id: str) -> List[AgentTimerEntry]:
        """获取某个 Agent 的所有定时器"""
        return [t for t in self._timers.values() if t.agent_id == agent_id]

    def get_timer(self, timer_id: str) -> Optional[AgentTimerEntry]:
        """获取单个定时器"""
        return self._timers.get(timer_id)

    def add_timer(self, timer: AgentTimerEntry) -> None:
        """添加定时器"""
        self._timers[timer.id] = timer
        if timer.enabled and self._running:
            self._schedule_timer(timer)
        self.save_timers()
        logger.info("Timer added", timer_id=timer.id, agent_id=timer.agent_id)

    def update_timer(self, timer_id: str, updates: Dict[str, Any]) -> Optional[AgentTimerEntry]:
        """更新定时器"""
        timer = self._timers.get(timer_id)
        if not timer:
            return None

        for key, value in updates.items():
            if hasattr(timer, key):
                setattr(timer, key, value)

        # 重新调度
        if self._running:
            self._unschedule_timer(timer_id)
            if timer.enabled:
                self._schedule_timer(timer)

        self.save_timers()
        logger.info("Timer updated", timer_id=timer_id)
        return timer

    def delete_timer(self, timer_id: str) -> bool:
        """删除定时器"""
        if timer_id not in self._timers:
            return False
        self._unschedule_timer(timer_id)
        del self._timers[timer_id]
        self.save_timers()
        logger.info("Timer deleted", timer_id=timer_id)
        return True

    def toggle_timer(self, timer_id: str, enabled: bool) -> Optional[AgentTimerEntry]:
        """启用/禁用定时器"""
        return self.update_timer(timer_id, {"enabled": enabled})

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            return
        self._running = True
        self.load_timers()

        # 调度所有启用的定时器
        for timer in self._timers.values():
            if timer.enabled:
                self._schedule_timer(timer)

        # 启动后台循环检查
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started", active_timers=len(self._jobs))

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._jobs.clear()
        logger.info("Scheduler stopped")

    def _schedule_timer(self, timer: AgentTimerEntry) -> None:
        """内部：调度单个定时器"""
        try:
            cron_params = _parse_cron(timer.cron_expression)
            self._jobs[timer.id] = {
                "timer": timer,
                "cron_params": cron_params,
                "next_check": datetime.now(),
            }
            logger.debug("Scheduled timer", timer_id=timer.id, cron=timer.cron_expression)
        except ValueError as e:
            logger.error("Failed to schedule timer", timer_id=timer.id, error=str(e))

    def _unschedule_timer(self, timer_id: str) -> None:
        """内部：取消调度"""
        self._jobs.pop(timer_id, None)

    async def _run_loop(self) -> None:
        """后台循环 - 每分钟检查是否有定时器需要触发"""
        while self._running:
            try:
                now = datetime.now()
                for timer_id, job_info in list(self._jobs.items()):
                    timer = job_info["timer"]
                    if self._should_fire(timer.cron_expression, now):
                        await self._fire_timer(timer)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error", error=str(e))

            # 每 60 秒检查一次
            await asyncio.sleep(60)

    def _should_fire(self, cron_expr: str, now: datetime) -> bool:
        """检查当前时间是否匹配 cron 表达式"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, dow = parts

        if minute != "*" and str(now.minute) != minute:
            return False
        if hour != "*" and str(now.hour) != hour:
            return False
        if day != "*" and str(now.day) != day:
            return False
        if month != "*" and str(now.month) != month:
            return False
        if dow != "*" and str(now.weekday()) != dow:
            return False

        return True

    async def _fire_timer(self, timer: AgentTimerEntry) -> None:
        """触发定时器执行"""
        logger.info("Firing timer", timer_id=timer.id, action=timer.action[:50])

        timer.last_run_at = datetime.now().isoformat()
        timer.run_count += 1

        try:
            if self._action_handler:
                await self._action_handler(timer)
            timer.last_run_status = "success"
            timer.last_run_error = None
        except Exception as e:
            timer.last_run_status = "error"
            timer.last_run_error = str(e)
            logger.error("Timer execution failed", timer_id=timer.id, error=str(e))

        self.save_timers()


# 全局单例
_scheduler: Optional[AgentScheduler] = None


def get_scheduler() -> AgentScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AgentScheduler()
    return _scheduler
