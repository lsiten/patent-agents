"""
依赖注入容器
使用 injector 实现服务注册与解析（纯Python实现，无需编译）
"""
from typing import Any, AsyncGenerator, Optional
from injector import Injector, singleton, Binder

from .config import settings
from .logging import get_logger
from .cache import create_cache_service
from .storage import create_storage_service
from src.repositories import (
    UnitOfWork,
    PatentTaskRepository, TaskEventRepository,
    RequirementDocRepository, RetrievalReportRepository,
    PatentDraftRepository, ReviewReportRepository,
    FinalPatentRepository, DocumentRepository,
    ChatSessionRepository, ChatMessageRepository,
    AgentRepository, AgentToolRepository, AgentSkillRepository, AgentMemoryRepository,
)

from src.services import (
    TaskService,
    PatentService,
    WorkflowService,
    ChatService,
)
from src.core.workflow_engine import PatentWorkflowEngine
from src.core.events import get_event_bus
from src.data_sources.base import get_data_source_manager
from src.knowledge.base import get_knowledge_base

logger = get_logger(__name__)


# ========== 数据库连接 Provider ==========

class DatabaseProvider:
    """数据库连接Provider"""

    def __init__(self, database_url: str, **kwargs):
        self.database_url = database_url
        self.engine = None
        self.async_session_factory = None
        self._kwargs = kwargs

    async def init(self) -> None:
        """初始化数据库连接"""
        from sqlalchemy.ext.asyncio import (
            AsyncEngine,
            AsyncSession,
            create_async_engine,
            async_sessionmaker,
        )

        logger.info("Initializing database connection", url=self.database_url)

        self.engine: AsyncEngine = create_async_engine(
            self.database_url,
            echo=self._kwargs.get("echo", settings.db.echo),
            pool_size=self._kwargs.get("pool_size", settings.db.pool_size),
            max_overflow=self._kwargs.get("max_overflow", settings.db.max_overflow),
            pool_recycle=self._kwargs.get("pool_recycle", settings.db.pool_recycle),
            pool_pre_ping=self._kwargs.get("pool_pre_ping", settings.db.pool_pre_ping),
        )

        self.async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info("Database connection initialized successfully")

    async def cleanup(self) -> None:
        """清理数据库连接"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")

    async def get_session(self) -> AsyncGenerator[Any, None]:
        """获取数据库会话"""
        if not self.async_session_factory:
            await self.init()

        async with self.async_session_factory() as session:
            yield session


# ========== Redis 连接 Provider ==========

class RedisProvider:
    """Redis连接Provider"""

    def __init__(self, redis_url: str, **kwargs):
        self.redis_url = redis_url
        self.redis = None
        self._kwargs = kwargs
        self._enabled = redis_url is not None

    async def init(self) -> None:
        """初始化Redis连接"""
        if not self._enabled:
            logger.warning("Redis not configured, skipping initialization")
            return

        try:
            import redis.asyncio as redis

            logger.info("Initializing Redis connection")

            self.redis = redis.from_url(
                self.redis_url,
                max_connections=self._kwargs.get(
                    "max_connections",
                    settings.redis.max_connections
                ),
                socket_timeout=self._kwargs.get(
                    "socket_timeout",
                    settings.redis.socket_timeout
                ),
                socket_connect_timeout=self._kwargs.get(
                    "socket_connect_timeout",
                    settings.redis.socket_connect_timeout
                ),
                retry_on_timeout=self._kwargs.get(
                    "retry_on_timeout",
                    settings.redis.retry_on_timeout
                ),
                decode_responses=True,
            )

            # 测试连接
            await self.redis.ping()
            logger.info("Redis connection initialized successfully")

        except ImportError:
            logger.warning("Redis library not installed, skipping initialization")
            self._enabled = False
        except Exception as e:
            logger.error(
                "Failed to initialize Redis connection",
                error=str(e)
            )
            self._enabled = False

    async def cleanup(self) -> None:
        """清理Redis连接"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

    def get_client(self) -> Optional[Any]:
        """获取Redis客户端"""
        return self.redis if self._enabled else None


# ========== LLM 服务 Provider ==========

class LLMServiceProvider:
    """LLM服务Provider"""

    def __init__(self, llm_config):
        self.config = llm_config
        self.openai_client = None
        self.anthropic_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        """初始化LLM客户端"""
        # OpenAI 客户端
        if self.config.openai_api_key:
            try:
                from openai import AsyncOpenAI

                self.openai_client = AsyncOpenAI(
                    api_key=self.config.openai_api_key,
                    base_url=self.config.openai_base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                )
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.error("Failed to initialize OpenAI client", error=str(e))

        # Anthropic 客户端
        if self.config.anthropic_api_key:
            try:
                from anthropic import AsyncAnthropic

                self.anthropic_client = AsyncAnthropic(
                    api_key=self.config.anthropic_api_key,
                    base_url=self.config.anthropic_base_url,
                    timeout=self.config.timeout,
                )
                logger.info("Anthropic client initialized")
            except Exception as e:
                logger.error("Failed to initialize Anthropic client", error=str(e))

    def get_openai_client(self):
        return self.openai_client

    def get_anthropic_client(self):
        return self.anthropic_client

    async def cleanup(self) -> None:
        """清理客户端"""
        if self.openai_client:
            await self.openai_client.close()
        if self.anthropic_client:
            await self.anthropic_client.close()
        logger.info("LLM clients cleaned up")


# ========== 全局服务实例（简化版） ==========

# 全局单例实例
_db_provider = None
_redis_provider = None
_llm_service = None
_event_bus = None
_data_source_manager = None
_knowledge_base = None
_workflow_engine = None
_cache_service = None
_storage_service = None


def get_db_provider() -> DatabaseProvider:
    """获取数据库Provider"""
    global _db_provider
    if _db_provider is None:
        _db_provider = DatabaseProvider(database_url=settings.db.url)
    return _db_provider


def get_redis_provider() -> RedisProvider:
    """获取RedisProvider"""
    global _redis_provider
    if _redis_provider is None:
        _redis_provider = RedisProvider(redis_url=settings.redis.url)
    return _redis_provider


def get_llm_service() -> LLMServiceProvider:
    """获取LLM服务"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMServiceProvider(llm_config=settings.llm)
    return _llm_service


def get_event_bus_instance() -> Any:
    """获取事件总线"""
    global _event_bus
    if _event_bus is None:
        _event_bus = get_event_bus()
    return _event_bus


def get_data_source_manager_instance() -> Any:
    """获取数据源管理器"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = get_data_source_manager()
    return _data_source_manager


def get_knowledge_base_instance() -> Any:
    """获取知识库"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = get_knowledge_base()
    return _knowledge_base


def get_workflow_engine() -> PatentWorkflowEngine:
    """获取工作流引擎"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = PatentWorkflowEngine()
    return _workflow_engine


def get_cache_service() -> Any:
    """获取缓存服务"""
    global _cache_service
    if _cache_service is None:
        _cache_service = create_cache_service(redis_client=get_redis_provider().get_client())
    return _cache_service


def get_storage_service() -> Any:
    """获取存储服务"""
    global _storage_service
    if _storage_service is None:
        _storage_service = create_storage_service()
    return _storage_service


def get_unit_of_work():
    """获取工作单元"""
    db = get_db_provider()
    if db.async_session_factory is None:
        # 延迟初始化
        import asyncio
        asyncio.run(db.init())
    return UnitOfWork(session_factory=db.async_session_factory)


# ========== 兼容旧API的容器代理 ==========

class ContainerProxy:
    """兼容 dependency-injector API 的代理类"""
    
    def __getattr__(self, name):
        # 处理 db_provider(), redis_provider() 等调用
        if name == 'db_provider':
            return get_db_provider
        elif name == 'redis_provider':
            return get_redis_provider
        elif name == 'redis_client':
            # 返回一个函数，该函数返回一个返回 redis 客户端的函数
            def wrapper():
                redis_provider = get_redis_provider()
                return lambda: redis_provider.get_client()
            return wrapper
        elif name == 'llm_service':
            return get_llm_service
        elif name == 'event_bus':
            return get_event_bus_instance
        elif name == 'data_source_manager':
            return get_data_source_manager_instance
        elif name == 'knowledge_base':
            return get_knowledge_base_instance
        elif name == 'workflow_engine':
            return get_workflow_engine
        elif name == 'cache_service':
            return get_cache_service
        elif name == 'storage_service':
            return get_storage_service
        elif name == 'unit_of_work':
            return get_unit_of_work
        raise AttributeError(f"Container has no attribute '{name}'")


# 创建全局容器代理实例
container = ContainerProxy()


# 兼容旧API的ApplicationContainer类
class ApplicationContainer:
    """兼容 dependency-injector 的 ApplicationContainer 类"""
    wiring_config = None
    
    def __init__(self):
        pass


async def init_container() -> None:
    """初始化容器"""
    logger.info("Initializing application container")

    # 初始化数据库
    db = get_db_provider()
    await db.init()

    from src.models.base import Base as ModelBase
    async with db.engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    logger.info("Database tables created / verified")

    # 初始化 Redis
    redis = get_redis_provider()
    await redis.init()

    logger.info("Application container initialized successfully")


async def cleanup_container() -> None:
    """清理容器资源"""
    logger.info("Cleaning up application container")

    # 清理 LLM 客户端
    llm_service = get_llm_service()
    await llm_service.cleanup()

    # 清理 Redis
    redis = get_redis_provider()
    await redis.cleanup()

    # 清理数据库
    db = get_db_provider()
    await db.cleanup()

    logger.info("Application container cleaned up successfully")
