"""
任务队列
Celery集成Redis broker，支持异步任务与定时任务
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, TypeVar
from functools import wraps

from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun, task_failure

from .config import settings
from .logging import get_logger
from .events import (
    publish_event,
    TaskProgressUpdatedEvent,
    TaskCompletedEvent,
)

logger = get_logger(__name__)

T = TypeVar("T")


# ========== Celery 应用配置 ==========

def create_celery_app() -> Optional[Celery]:
    """创建Celery应用"""
    if not settings.celery.broker_url or not settings.celery.result_backend:
        logger.warning("Celery broker/backend not configured, running tasks synchronously")
        return None

    celery_app = Celery("patent_agents")

    # 配置
    celery_app.conf.update(
        broker_url=settings.celery.broker_url,
        result_backend=settings.celery.result_backend,
        task_serializer=settings.celery.task_serializer,
        result_serializer=settings.celery.result_serializer,
        accept_content=settings.celery.accept_content,
        timezone=settings.celery.timezone,
        enable_utc=settings.celery.enable_utc,
        task_track_started=settings.celery.task_track_started,
        task_time_limit=settings.celery.task_time_limit,
        task_soft_time_limit=settings.celery.task_soft_time_limit,
        worker_prefetch_multiplier=settings.celery.worker_prefetch_multiplier,
        worker_max_tasks_per_child=settings.celery.worker_max_tasks_per_child,
        # 失败重试配置
        task_default_retry_delay=30,  # 30秒
        task_max_retries=3,
        # 结果过期时间
        result_expires=86400,  # 24小时
    )

    # 自动发现任务
    celery_app.autodiscover_tasks([
        "src.core",
        "src.agents",
        "src.services",
    ])

    logger.info("Celery app initialized")
    return celery_app


# 全局Celery应用实例
celery_app = create_celery_app()


# ========== 异步任务装饰器 ==========

def async_task(bind: bool = False, **task_kwargs):
    """
    异步任务装饰器
    自动处理Celery配置，优雅降级（无Broker时同步执行）

    使用方式:
        @async_task
        def my_task(param1, param2):
            ...

        @async_task(bind=True, max_retries=3)
        def my_task_with_self(self, param1):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if celery_app is None:
                # 无Broker时同步执行
                logger.debug("Running task synchronously", task=func.__name__)
                return func(*args, **kwargs)

            # 有Broker时通过Celery执行
            task_decorator = celery_app.task(bind=bind, **task_kwargs)
            return task_decorator(func)(*args, **kwargs)

        return wrapper
    return decorator


# ========== 工作流任务定义 ==========

@async_task(bind=True, max_retries=1, soft_time_limit=300)
def run_patent_workflow_task(self, task_id: str, user_id: str, tech_description: str) -> Dict[str, Any]:
    """
    执行专利申请工作流的异步任务
    这是一个长时间运行的任务，包含多个Agent的协同工作
    """
    logger.info("Starting patent workflow", task_id=task_id, user_id=user_id)

    # 同步调用异步工作流（在Celery worker中运行事件循环）
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        _run_workflow_async(self, task_id, user_id, tech_description)
    )

    return result


async def _run_workflow_async(task_instance, task_id: str, user_id: str, tech_description: str) -> Dict[str, Any]:
    """异步执行工作流"""
    try:
        from .workflow import PatentWorkflowOrchestrator

        # 创建工作流编排器
        orchestrator = PatentWorkflowOrchestrator(task_id=task_id, user_id=user_id)

        # 发布开始事件
        await publish_event(TaskProgressUpdatedEvent(
            task_id=task_id,
            user_id=user_id,
            state="started",
            progress=0,
            message="工作流开始执行",
        ))

        # 执行工作流
        result = await orchestrator.run(tech_description=tech_description)

        # 发布完成事件
        await publish_event(TaskCompletedEvent(
            task_id=task_id,
            user_id=user_id,
            result=result,
        ))

        return {
            "task_id": task_id,
            "status": "completed",
            "result": result,
        }

    except Exception as e:
        logger.error("Workflow task failed", task_id=task_id, error=str(e), exc_info=True)
        await publish_event(TaskProgressUpdatedEvent(
            task_id=task_id,
            user_id=user_id,
            state="failed",
            progress=100,
            message=f"工作流执行失败: {str(e)}",
        ))
        raise


@async_task(max_retries=2, soft_time_limit=120)
def run_agent_task(
    agent_name: str,
    task_id: str,
    user_id: str,
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    执行单个Agent任务
    """
    logger.info("Running agent task", agent_name=agent_name, task_id=task_id)

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        _run_agent_async(agent_name, task_id, user_id, input_data)
    )

    return result


async def _run_agent_async(
    agent_name: str,
    task_id: str,
    user_id: str,
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    """异步执行Agent"""
    try:
        from src.agents import get_agent_by_name

        agent = get_agent_by_name(agent_name)
        if not agent:
            raise ValueError(f"Agent not found: {agent_name}")

        result = await agent.run(**input_data)

        return {
            "agent_name": agent_name,
            "task_id": task_id,
            "status": "completed",
            "output": result,
        }

    except Exception as e:
        logger.error(
            "Agent task failed",
            agent_name=agent_name,
            task_id=task_id,
            error=str(e),
        )
        raise


# ========== 定时任务定义 ==========

@async_task
def cleanup_expired_tasks() -> Dict[str, Any]:
    """清理过期任务"""
    logger.info("Running cleanup expired tasks job")

    # TODO: 实现清理逻辑
    # 1. 删除超过30天的已完成任务
    # 2. 清理过期的临时文件
    # 3. 归档旧数据

    return {
        "status": "completed",
        "cleanup_time": datetime.now().isoformat(),
    }


@async_task
def generate_daily_report() -> Dict[str, Any]:
    """生成每日统计报告"""
    logger.info("Running daily report job")

    # TODO: 实现报告生成
    # 1. 统计当天任务数
    # 2. 统计成功率
    # 3. 平均执行时间
    # 4. Agent使用情况

    return {
        "status": "completed",
        "report_time": datetime.now().isoformat(),
    }


@async_task
def health_check() -> Dict[str, Any]:
    """系统健康检查"""
    logger.debug("Running health check")

    # TODO: 实现健康检查
    # 1. 数据库连接
    # 2. Redis连接
    # 3. LLM API可用性
    # 4. Agent状态

    return {
        "status": "healthy",
        "check_time": datetime.now().isoformat(),
    }


# ========== 定时任务配置 ==========

def configure_periodic_tasks(app: Celery) -> None:
    """配置定时任务"""
    app.conf.beat_schedule = {
        # 每小时执行一次清理
        "cleanup-expired-tasks": {
            "task": "src.core.tasks.cleanup_expired_tasks",
            "schedule": timedelta(hours=1),
        },
        # 每天凌晨2点生成日报
        "generate-daily-report": {
            "task": "src.core.tasks.generate_daily_report",
            "schedule": crontab(hour=2, minute=0),
        },
        # 每5分钟执行健康检查
        "health-check": {
            "task": "src.core.tasks.health_check",
            "schedule": timedelta(minutes=5),
        },
    }

    logger.info("Periodic tasks configured")


# 如果Celery可用，配置定时任务
if celery_app:
    configure_periodic_tasks(celery_app)


# ========== 任务事件处理 ==========

@task_prerun.connect
def on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """任务开始前的钩子"""
    logger.info(
        "Task starting",
        task_name=task.name if task else "unknown",
        task_id=task_id,
    )


@task_postrun.connect
def on_task_postrun(sender=None, task_id=None, task=None, args=None, kwargs=None,
                    retval=None, state=None, **kw):
    """任务完成后的钩子"""
    logger.info(
        "Task completed",
        task_name=task.name if task else "unknown",
        task_id=task_id,
        state=state,
    )


@task_failure.connect
def on_task_failure(sender=None, task_id=None, task=None, args=None, kwargs=None,
                    exception=None, traceback=None, einfo=None, **kw):
    """任务失败的钩子"""
    logger.error(
        "Task failed",
        task_name=task.name if task else "unknown",
        task_id=task_id,
        exception=str(exception),
    )


# ========== 任务执行器（用于本地执行，不通过Celery） ==========

class LocalTaskExecutor:
    """
    本地任务执行器
    在没有Celery Broker的情况下，直接在当前进程执行任务
    适合开发环境和单实例部署
    """

    def __init__(self):
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._logger = get_logger("local_executor")

    async def run_task(self, coro, task_id: str) -> Any:
        """执行任务"""
        try:
            task = asyncio.create_task(coro)
            self._running_tasks[task_id] = task

            result = await task
            return result

        except asyncio.CancelledError:
            self._logger.info("Task cancelled", task_id=task_id)
            raise
        finally:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            return True
        return False

    def get_running_tasks(self) -> list[str]:
        """获取运行中的任务列表"""
        return list(self._running_tasks.keys())


# 全局本地执行器实例
local_executor = LocalTaskExecutor()


# ========== 便捷函数 ==========

def submit_workflow_task(task_id: str, user_id: str, tech_description: str) -> str:
    """
    提交工作流任务
    返回任务ID
    """
    if celery_app:
        # 使用Celery异步执行
        result = run_patent_workflow_task.delay(task_id, user_id, tech_description)
        logger.info("Workflow task submitted to Celery", celery_task_id=result.id)
        return result.id
    else:
        # 使用本地执行器（异步在事件循环中运行）
        asyncio.create_task(
            _run_workflow_async(None, task_id, user_id, tech_description)
        )
        logger.info("Workflow task submitted to local executor")
        return task_id


def cancel_task(celery_task_id: str, patent_task_id: Optional[str] = None) -> bool:
    """
    取消任务
    """
    if celery_app:
        celery_app.control.revoke(celery_task_id, terminate=True)
        return True
    elif patent_task_id:
        return local_executor.cancel_task(patent_task_id)
    return False
