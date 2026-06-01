"""
依赖注入容器
使用 dependency-injector 实现服务注册与解析
"""
from typing import Any, AsyncGenerator, Optional
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

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


# ========== 应用容器 ==========

class ApplicationContainer(containers.DeclarativeContainer):
    """应用主容器"""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "__main__",
            "src.api.routes",
            "src.core.middleware",
            "src.utils",
            "src.utils.time_utils",
            "src.utils.text_utils",
        ],
        auto_wire=True,
    )

    # 配置
    config = providers.Configuration(pydantic_settings=[settings])

    # 日志
    logger = providers.Singleton(get_logger, name="app")

    # 数据库
    db_provider = providers.Singleton(
        DatabaseProvider,
        database_url=config.db.url,
    )

    db_session = providers.Resource(
        db_provider.provided.get_session,
    )

    # Redis
    redis_provider = providers.Singleton(
        RedisProvider,
        redis_url=config.redis.url,
    )

    redis_client = providers.Factory(
        redis_provider.provided.get_client,
    )

    # LLM 服务
    llm_service = providers.Singleton(
        LLMServiceProvider,
        llm_config=config.llm,
    )

    # 缓存服务
    cache_service = providers.Singleton(
        lambda: create_cache_service(
            redis_client=container.redis_client(),
        )
    )

    # 存储服务
    storage_service = providers.Singleton(
        lambda: create_storage_service()
    )

    # Session factory (lazy — resolved after db_provider.init())
    session_factory = providers.Singleton(
        lambda: container.db_provider().async_session_factory
    )

    # Unit of Work (per-request transaction boundary)
    unit_of_work = providers.Factory(
        UnitOfWork,
        session_factory=session_factory,
    )

    # Repository (wired via UoW — see unit_of_work.*_repository)
    # Direct factory wiring for services that need single repos
    patent_task_repository = providers.Factory(
        PatentTaskRepository, session=db_provider.provided.get_session.call()
    )
    agent_repository = providers.Factory(
        AgentRepository, session=db_provider.provided.get_session.call()
    )
    chat_session_repository = providers.Factory(
        ChatSessionRepository, session=db_provider.provided.get_session.call()
    )

    # ── 基础设施单例 ─────────────────────────────────────
    event_bus = providers.Singleton(get_event_bus)
    data_source_manager = providers.Singleton(get_data_source_manager)
    knowledge_base = providers.Singleton(get_knowledge_base)

    # ── 工作流引擎 ───────────────────────────────────────
    workflow_engine = providers.Singleton(PatentWorkflowEngine)

    # ── 服务层 ───────────────────────────────────────────
    task_service = providers.Singleton(
        TaskService,
        uow_factory=lambda: container.unit_of_work(),
    )
    patent_service = providers.Singleton(
        PatentService,
        data_source_manager=data_source_manager,
        knowledge_base=knowledge_base,
    )
    workflow_service = providers.Singleton(
        WorkflowService,
        workflow_engine=workflow_engine,
        event_bus=event_bus,
    )
    chat_service = providers.Factory(
        ChatService,
        uow_factory=lambda: container.unit_of_work(),
        workflow_service=workflow_service,
    )


# 全局容器实例
container = ApplicationContainer()


async def init_container() -> None:
    """初始化容器"""
    logger.info("Initializing application container")

    # 初始化数据库
    db = container.db_provider()
    await db.init()

    from src.models.base import Base as ModelBase
    async with db.engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    logger.info("Database tables created / verified")

    # 初始化 Redis
    redis = container.redis_provider()
    await redis.init()

    logger.info("Application container initialized successfully")


async def cleanup_container() -> None:
    """清理容器资源"""
    logger.info("Cleaning up application container")

    # 清理 LLM 客户端
    llm_service = container.llm_service()
    await llm_service.cleanup()

    # 清理 Redis
    redis = container.redis_provider()
    await redis.cleanup()

    # 清理数据库
    db = container.db_provider()
    await db.cleanup()

    logger.info("Application container cleaned up successfully")
