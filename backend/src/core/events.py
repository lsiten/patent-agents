"""
事件总线
实现发布订阅模式，支持内存事件总线和Redis事件总线
"""
import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from uuid import uuid4

from .logging import get_logger
from .middleware import sse_manager

logger = get_logger(__name__)

T = TypeVar("T", bound="BaseEvent")


class EventType(str, Enum):
    """事件类型枚举"""
    # 系统事件
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # 用户事件
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"

    # 任务事件
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # 工作流事件
    WORKFLOW_STATE_CHANGED = "workflow.state_changed"
    WORKFLOW_PROGRESS_UPDATED = "workflow.progress_updated"
    WORKFLOW_ITERATION_COMPLETED = "workflow.iteration_completed"

    # Agent 事件
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_THINKING = "agent.thinking"
    AGENT_TOOL_CALL_START = "agent.tool_call_start"
    AGENT_TOOL_CALL_END = "agent.tool_call_end"
    AGENT_DISPATCH = "agent.dispatch"
    AGENT_CONTENT = "agent.content"

    # 聊天事件
    CHAT_MESSAGE_CREATED = "chat.message.created"
    CHAT_BRAINSTORMING_UPDATED = "chat.brainstorming_updated"

    # 专利事件
    PATENT_DRAFT_CREATED = "patent.draft_created"
    PATENT_REVIEW_COMPLETED = "patent.review_completed"
    PATENT_BRAINSTORMING_COMPLETED = "patent.brainstorming_completed"
    PATENT_FINALIZED = "patent.finalized"

    # 组织事件
    ORGANIZATION_CREATED = "organization.created"
    ORGANIZATION_UPDATED = "organization.updated"


@dataclass
class BaseEvent:
    """事件基类"""
    event_type: EventType = EventType.SYSTEM_ERROR  # 子类 __post_init__ 会覆盖
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "version": self.version,
            "metadata": self.metadata,
            **self._get_payload_dict(),
        }

    def _get_payload_dict(self) -> Dict[str, Any]:
        """获取事件负载字典 - 由子类实现"""
        return {}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        return cls(**data)


# ========== 具体事件定义 ==========

@dataclass
class TaskProgressUpdatedEvent(BaseEvent):
    """任务进度更新事件"""
    task_id: str = ""
    user_id: str = ""
    state: str = ""
    progress: int = 0
    message: str = ""
    agent_name: Optional[str] = None

    def __post_init__(self):
        self.event_type = EventType.WORKFLOW_PROGRESS_UPDATED

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "state": self.state,
            "progress": self.progress,
            "message": self.message,
            "agent_name": self.agent_name,
        }


@dataclass
class AgentThinkingEvent(BaseEvent):
    """Agent思考事件"""
    task_id: str = ""
    user_id: str = ""
    agent_name: str = ""
    thought: str = ""
    step: int = 0

    def __post_init__(self):
        self.event_type = EventType.AGENT_THINKING

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "thought": self.thought,
            "step": self.step,
        }


@dataclass
class AgentToolCallStartEvent(BaseEvent):
    """Agent工具调用开始事件"""
    task_id: str = ""
    user_id: str = ""
    agent_name: str = ""
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = EventType.AGENT_TOOL_CALL_START

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
        }


@dataclass
class AgentToolCallEndEvent(BaseEvent):
    """Agent工具调用完成事件"""
    task_id: str = ""
    user_id: str = ""
    agent_name: str = ""
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: str = ""
    success: bool = True

    def __post_init__(self):
        self.event_type = EventType.AGENT_TOOL_CALL_END

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class AgentDispatchEvent(BaseEvent):
    """CEO调度子Agent事件"""
    task_id: str = ""
    user_id: str = ""
    from_agent: str = ""
    to_agent: str = ""
    task_description: str = ""

    def __post_init__(self):
        self.event_type = EventType.AGENT_DISPATCH

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_description": self.task_description,
        }


@dataclass
class AgentContentEvent(BaseEvent):
    """Agent最终输出内容事件"""
    task_id: str = ""
    user_id: str = ""
    agent_name: str = ""
    content: str = ""
    phase: str = ""

    def __post_init__(self):
        self.event_type = EventType.AGENT_CONTENT

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "content": self.content,
            "phase": self.phase,
        }


@dataclass
class TaskCompletedEvent(BaseEvent):
    """任务完成事件"""
    task_id: str = ""
    user_id: str = ""
    result: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = EventType.TASK_COMPLETED

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "result": self.result,
        }


@dataclass
class ChatMessageEvent(BaseEvent):
    """聊天消息事件"""
    task_id: str = ""
    user_id: str = ""
    message_id: str = ""
    role: str = ""
    content: str = ""

    def __post_init__(self):
        self.event_type = EventType.CHAT_BRAINSTORMING_UPDATED

    def _get_payload_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
        }


# ========== 事件总线接口 ==========

class EventBus(ABC):
    """事件总线接口"""

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: Callable[[BaseEvent], None]) -> None:
        """订阅事件"""
        pass

    @abstractmethod
    async def publish(self, event: BaseEvent) -> None:
        """发布事件"""
        pass

    @abstractmethod
    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """取消订阅"""
        pass


# ========== 内存事件总线 ==========

class InMemoryEventBus(EventBus):
    """内存事件总线实现"""

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable[[BaseEvent], None]]] = {}
        self._sse_events = {
            EventType.WORKFLOW_PROGRESS_UPDATED,
            EventType.AGENT_THINKING,
            EventType.AGENT_TOOL_CALL_START,
            EventType.AGENT_TOOL_CALL_END,
            EventType.AGENT_DISPATCH,
            EventType.AGENT_CONTENT,
            EventType.CHAT_BRAINSTORMING_UPDATED,
            EventType.TASK_COMPLETED,
        }

    def subscribe(self, event_type: EventType, handler: Callable[[BaseEvent], None]) -> None:
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed to event", event_type=event_type.value)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """取消订阅"""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]
            logger.debug("Unsubscribed from event", event_type=event_type.value)

    async def publish(self, event: BaseEvent) -> None:
        """发布事件"""
        logger.debug(
            "Publishing event",
            event_type=event.event_type.value,
            event_id=event.event_id,
        )

        # 调用订阅者
        if event.event_type in self._subscribers:
            for handler in self._subscribers[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(
                        "Event handler failed",
                        event_type=event.event_type.value,
                        error=str(e),
                        exc_info=True,
                    )

        # 向前端推送SSE事件
        if event.event_type in self._sse_events:
            await self._push_to_sse(event)

    async def _push_to_sse(self, event: BaseEvent) -> None:
        """推送事件到SSE"""
        try:
            event_dict = event.to_dict()
            user_id = getattr(event, "user_id", None)

            if user_id:
                await sse_manager.send_event(
                    user_id=user_id,
                    event=event.event_type.value,
                    data=json.dumps(event_dict, ensure_ascii=False),
                )
                logger.debug(
                    "Pushed event to SSE",
                    event_type=event.event_type.value,
                    user_id=user_id,
                )
        except Exception as e:
            logger.warning(
                "Failed to push event to SSE",
                event_type=event.event_type.value,
                error=str(e),
            )


# ========== Redis 事件总线（用于分布式部署） ==========

class RedisEventBus(EventBus):
    """基于Redis的事件总线"""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._in_memory_bus = InMemoryEventBus()
        self._channel = "patent_agent_events"
        self._listener_task: Optional[asyncio.Task] = None

    async def start_listener(self):
        """启动Redis事件监听器"""
        if not self._redis:
            logger.warning("Redis not available, falling back to in-memory event bus")
            return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)

        async def listener():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            event_type = EventType(data["event_type"])
                            event = self._create_event_from_data(event_type, data)
                            await self._in_memory_bus.publish(event)
                        except Exception as e:
                            logger.error("Failed to process Redis event", error=str(e))
            except asyncio.CancelledError:
                await pubsub.unsubscribe(self._channel)
                await pubsub.close()

        self._listener_task = asyncio.create_task(listener())

    async def stop_listener(self):
        """停止Redis事件监听器"""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

    def _create_event_from_data(self, event_type: EventType, data: Dict) -> BaseEvent:
        """根据事件类型创建具体事件实例"""
        event_classes = {
            EventType.WORKFLOW_PROGRESS_UPDATED: TaskProgressUpdatedEvent,
            EventType.AGENT_THINKING: AgentThinkingEvent,
            EventType.AGENT_TOOL_CALL_START: AgentToolCallStartEvent,
            EventType.AGENT_TOOL_CALL_END: AgentToolCallEndEvent,
            EventType.AGENT_DISPATCH: AgentDispatchEvent,
            EventType.AGENT_CONTENT: AgentContentEvent,
            EventType.TASK_COMPLETED: TaskCompletedEvent,
            EventType.CHAT_BRAINSTORMING_UPDATED: ChatMessageEvent,
        }
        event_class = event_classes.get(event_type, BaseEvent)
        return event_class.from_dict(data)

    def subscribe(self, event_type: EventType, handler: Callable[[BaseEvent], None]) -> None:
        """订阅事件"""
        self._in_memory_bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """取消订阅"""
        self._in_memory_bus.unsubscribe(event_type, handler)

    async def publish(self, event: BaseEvent) -> None:
        """发布事件"""
        # 先发布到内存（本地进程）
        await self._in_memory_bus.publish(event)

        # 再发布到Redis（跨进程）
        if self._redis:
            try:
                await self._redis.publish(self._channel, event.to_json())
            except Exception as e:
                logger.warning("Failed to publish to Redis", error=str(e))


# 全局事件总线实例（延迟初始化）
_event_bus: Optional[EventBus] = None


def get_event_bus(redis_client=None) -> EventBus:
    """获取事件总线实例"""
    global _event_bus
    if _event_bus is None:
        if redis_client:
            _event_bus = RedisEventBus(redis_client)
        else:
            _event_bus = InMemoryEventBus()
    return _event_bus


async def init_event_bus(redis_client=None) -> EventBus:
    """初始化事件总线"""
    bus = get_event_bus(redis_client)

    if isinstance(bus, RedisEventBus):
        await bus.start_listener()

    logger.info("Event bus initialized", type=bus.__class__.__name__)
    return bus


# 便捷发布函数
async def publish_event(event: BaseEvent) -> None:
    """发布事件的便捷函数"""
    bus = get_event_bus()
    await bus.publish(event)


# 便捷订阅函数
def subscribe_event(event_type: EventType, handler: Callable[[BaseEvent], None]) -> None:
    """订阅事件的便捷函数"""
    bus = get_event_bus()
    bus.subscribe(event_type, handler)
