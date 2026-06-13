# -*- coding: utf-8 -*-
"""
核心模块
包含配置、日志、异常处理、依赖注入、中间件、事件总线、任务队列、缓存、存储
"""

from .config import (
    settings,
    Environment,
    LogLevel,
    DatabaseSettings,
    RedisSettings,
    LLMSettings,
    SecuritySettings,
    PatentDBSettings,
    WorkflowSettings,
    StorageSettings,
    CelerySettings,
    AppSettings,
)

from .logging import (
    get_logger,
    configure_logging,
    Loggable,
    log_request_middleware,
    RequestIDContext,
)

from .exceptions import (
    ErrorCode,
    ErrorSeverity,
    ErrorDetail,
    BaseAppException,
    register_exception_handlers,
    # 系统异常
    InternalError,
    DatabaseError,
    TimeoutError,
    RateLimitExceeded,
    # 业务异常
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    InvalidStateTransitionError,
    BusinessRuleViolationError,
    # Agent异常
    AgentError,
    AgentTimeoutError,
    LLMAPIError,
    # 工作流异常
    WorkflowTimeoutError,
    WorkflowNotFoundError,
    TaskCancelledError,
    IterationLimitExceededError,
)

from .cache import (
    CacheBackend,
    MemoryCacheBackend,
    RedisCacheBackend,
    CacheService,
    create_cache_service,
    get_cache,
)

from .storage import (
    StorageBackend,
    LocalStorageBackend,
    MinioStorageBackend,
    StorageService,
    create_storage_service,
    get_storage,
)

from .container import (
    ApplicationContainer,
    container,
    init_container,
    cleanup_container,
    DatabaseProvider,
    RedisProvider,
    LLMServiceProvider,
)

from .middleware import (
    register_middleware,
    limiter,
    rate_limit,
    sse_manager,
    SSEConnectionManager,
)

from .events import (
    EventType,
    BaseEvent,
    EventBus,
    InMemoryEventBus,
    RedisEventBus,
    get_event_bus,
    init_event_bus,
    publish_event,
    subscribe_event,
    # 具体事件
    TaskProgressUpdatedEvent,
    AgentThinkingEvent,
    TaskCompletedEvent,
    ChatMessageEvent,
)

from .tasks import (
    celery_app,
    async_task,
    run_patent_workflow_task,
    run_agent_task,
    cleanup_expired_tasks,
    generate_daily_report,
    health_check,
    submit_workflow_task,
    cancel_task,
    local_executor,
    LocalTaskExecutor,
)

__all__ = [
    # config
    "settings",
    "Environment",
    "LogLevel",
    "DatabaseSettings",
    "RedisSettings",
    "LLMSettings",
    "SecuritySettings",
    "PatentDBSettings",
    "WorkflowSettings",
    "StorageSettings",
    "CelerySettings",
    "AppSettings",
    # logging
    "get_logger",
    "configure_logging",
    "Loggable",
    "log_request_middleware",
    "RequestIDContext",
    # exceptions
    "ErrorCode",
    "ErrorSeverity",
    "ErrorDetail",
    "BaseAppException",
    "register_exception_handlers",
    "InternalError",
    "DatabaseError",
    "TimeoutError",
    "RateLimitExceeded",
    "ResourceNotFoundError",
    "ResourceAlreadyExistsError",
    "InvalidStateTransitionError",
    "BusinessRuleViolationError",
    "AgentError",
    "AgentTimeoutError",
    "LLMAPIError",
    "WorkflowTimeoutError",
    "WorkflowNotFoundError",
    "TaskCancelledError",
    "IterationLimitExceededError",
    # container
    "ApplicationContainer",
    "container",
    "init_container",
    "cleanup_container",
    "DatabaseProvider",
    "RedisProvider",
    "LLMServiceProvider",
    # middleware
    "register_middleware",
    "limiter",
    "rate_limit",
    "sse_manager",
    "SSEConnectionManager",
    # events
    "EventType",
    "BaseEvent",
    "EventBus",
    "InMemoryEventBus",
    "RedisEventBus",
    "get_event_bus",
    "init_event_bus",
    "publish_event",
    "subscribe_event",
    "TaskProgressUpdatedEvent",
    "AgentThinkingEvent",
    "TaskCompletedEvent",
    "ChatMessageEvent",
    # tasks
    "celery_app",
    "async_task",
    "run_patent_workflow_task",
    "run_agent_task",
    "cleanup_expired_tasks",
    "generate_daily_report",
    "health_check",
    "submit_workflow_task",
    "cancel_task",
    "local_executor",
    "LocalTaskExecutor",
    # cache
    "CacheBackend",
    "MemoryCacheBackend",
    "RedisCacheBackend",
    "CacheService",
    "create_cache_service",
    "get_cache",
    # storage
    "StorageBackend",
    "LocalStorageBackend",
    "MinioStorageBackend",
    "StorageService",
    "create_storage_service",
    "get_storage",
]
