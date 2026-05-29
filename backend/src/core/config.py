"""
项目配置系统 - 使用 Pydantic Settings 实现
支持环境变量、.env 文件、配置验证
"""
import os
from enum import Enum
from typing import List, Optional, Union
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

# 显式加载 .env 文件到 os.environ，确保嵌套模型也能读取环境变量
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
if os.path.isfile(_env_path):
    load_dotenv(_env_path)


class Environment(str, Enum):
    """运行环境枚举"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseSettings(BaseSettings):
    """数据库配置"""
    url: str = Field(
        default="sqlite+aiosqlite:///./patent_agents.db",
        description="数据库连接URL",
        alias="DATABASE_URL"
    )
    echo: bool = Field(default=False, description="是否打印SQL语句")
    pool_size: int = Field(default=20, description="连接池大小")
    max_overflow: int = Field(default=10, description="最大溢出连接数")
    pool_recycle: int = Field(default=3600, description="连接回收时间(秒)")
    pool_pre_ping: bool = Field(default=True, description="连接预检查")

    model_config = {"env_prefix": "DB_"}


class RedisSettings(BaseSettings):
    """Redis 配置"""
    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis连接URL",
        alias="REDIS_URL"
    )
    max_connections: int = Field(default=50, description="最大连接数")
    socket_timeout: int = Field(default=5, description="套接字超时(秒)")
    socket_connect_timeout: int = Field(default=5, description="连接超时(秒)")
    retry_on_timeout: bool = Field(default=True, description="超时重试")

    model_config = {"env_prefix": "REDIS_"}


class LLMSettings(BaseSettings):
    """LLM API 配置"""
    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="OPENAI_BASE_URL"
    )
    llm_model: str = Field(default="gpt-4-turbo-preview", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096)
    llm_timeout: int = Field(default=120, description="LLM请求超时(秒)")

    # Anthropic Claude
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1",
        alias="ANTHROPIC_BASE_URL"
    )
    claude_model: str = Field(default="claude-3-opus-20240229")

    # Fallback 配置
    enable_fallback: bool = Field(default=True, description="启用LLM降级策略")
    fallback_order: List[str] = Field(
        default_factory=lambda: ["openai", "anthropic"]
    )

    # Retry 配置
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟(秒)")

    model_config = {"env_prefix": "LLM_"}

    @field_validator("fallback_order")
    @classmethod
    def validate_fallback_order(cls, v: List[str]) -> List[str]:
        valid_providers = {"openai", "anthropic"}
        if not all(p in valid_providers for p in v):
            raise ValueError(f"Fallback providers must be one of {valid_providers}")
        return v


class SecuritySettings(BaseSettings):
    """安全配置"""
    api_secret_key: str = Field(
        default="change_this_in_production",
        description="API签名密钥",
        alias="API_SECRET_KEY"
    )
    jwt_secret_key: str = Field(
        default="change_this_in_production",
        description="JWT签名密钥",
        alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(
        default=1440,
        description="JWT过期时间(分钟)",
        alias="JWT_EXPIRE_MINUTES"
    )
    cors_allowed_origins: List[str] = Field(
        default_factory=lambda: ["*"],
        alias="CORS_ALLOWED_ORIGINS"
    )
    rate_limit_enabled: bool = Field(default=True, description="启用速率限制")
    rate_limit_requests: int = Field(default=100, description="每分钟请求限制")

    model_config = {"env_prefix": "SECURITY_"}

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


class PatentDBSettings(BaseSettings):
    """专利数据库API配置"""
    # USPTO
    uspto_api_key: Optional[str] = Field(default=None, alias="USPTO_API_KEY")
    uspto_api_url: str = Field(
        default="https://developer.uspto.gov/ibd-api/v1",
        alias="USPTO_API_URL"
    )

    # EPO
    epo_consumer_key: Optional[str] = Field(default=None, alias="EPO_CONSUMER_KEY")
    epo_consumer_secret: Optional[str] = Field(
        default=None,
        alias="EPO_CONSUMER_SECRET"
    )

    # CNIPA
    cnipa_api_token: Optional[str] = Field(default=None, alias="CNIPA_API_TOKEN")

    # Google Patents
    enable_google_patents: bool = Field(default=True, alias="ENABLE_GOOGLE_PATENTS")

    # arXiv
    enable_arxiv: bool = Field(default=True, alias="ENABLE_ARXIV")

    model_config = {"env_prefix": "PATENT_DB_"}


class WorkflowSettings(BaseSettings):
    """工作流配置"""
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="最大迭代次数",
        alias="MAX_ITERATIONS"
    )

    # Agent 开关
    enable_requirement_analyst: bool = Field(
        default=True,
        alias="ENABLE_REQUIREMENT_ANALYST"
    )
    enable_retrieval_analyst: bool = Field(
        default=True,
        alias="ENABLE_RETRIEVAL_ANALYST"
    )
    enable_patent_writer: bool = Field(
        default=True,
        alias="ENABLE_PATENT_WRITER"
    )
    enable_quality_reviewer: bool = Field(
        default=True,
        alias="ENABLE_QUALITY_REVIEWER"
    )

    # 超时配置
    task_timeout: int = Field(default=3600, description="任务总超时(秒)")
    agent_timeout: int = Field(default=600, description="单Agent执行超时(秒)")

    model_config = {"env_prefix": "WORKFLOW_"}


class StorageSettings(BaseSettings):
    """存储配置"""
    # 本地存储
    knowledge_base_path: str = Field(
        default="./finalized_patents",
        alias="KNOWLEDGE_BASE_PATH"
    )
    finalized_patents_docx_path: str = Field(
        default="./定稿文件",
        alias="FINALIZED_PATENTS_DOCX_PATH",
        description="定稿专利 docx 文件目录，每个子目录为一个专利（含 A/B 文件）"
    )
    export_path: str = Field(default="./exports", alias="EXPORT_PATH")
    export_formats: List[str] = Field(
        default_factory=lambda: ["json", "md", "docx"],
        alias="EXPORT_FORMATS"
    )

    # MinIO/S3 对象存储
    minio_endpoint: Optional[str] = Field(default=None, alias="MINIO_ENDPOINT")
    minio_access_key: Optional[str] = Field(default=None, alias="MINIO_ACCESS_KEY")
    minio_secret_key: Optional[str] = Field(default=None, alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="patent-documents", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=True, alias="MINIO_SECURE")

    # Vector Search
    enable_vector_search: bool = Field(default=False, alias="ENABLE_VECTOR_SEARCH")
    vector_dimension: int = Field(default=1536, description="向量维度")

    model_config = {"env_prefix": "STORAGE_"}

    @field_validator("export_formats", mode="before")
    @classmethod
    def parse_export_formats(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [fmt.strip().lower() for fmt in v.split(",")]
        return v


class CelerySettings(BaseSettings):
    """Celery任务队列配置"""
    broker_url: Optional[str] = Field(default=None, alias="CELERY_BROKER_URL")
    result_backend: Optional[str] = Field(default=None, alias="CELERY_RESULT_BACKEND")
    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    accept_content: List[str] = Field(default_factory=lambda: ["json"])
    timezone: str = Field(default="Asia/Shanghai")
    enable_utc: bool = Field(default=True)
    task_track_started: bool = Field(default=True)
    task_time_limit: int = Field(default=3600, description="任务硬超时(秒)")
    task_soft_time_limit: int = Field(default=3300, description="任务软超时(秒)")
    worker_prefetch_multiplier: int = Field(default=1)
    worker_max_tasks_per_child: int = Field(default=1000)

    model_config = {"env_prefix": "CELERY_"}


class AppSettings(BaseSettings):
    """应用主配置"""
    # 基础配置
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, ge=1, le=65535, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="运行环境"
    )
    log_level: LogLevel = Field(default=LogLevel.INFO, alias="LOG_LEVEL")
    app_name: str = Field(default="专利申请多智能体系统")
    api_version: str = Field(default="/api/v1")
    root_path: str = Field(default="", description="API根路径前缀")

    # 子配置
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    patent_db: PatentDBSettings = Field(default_factory=PatentDBSettings)
    workflow: WorkflowSettings = Field(default_factory=WorkflowSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

    @model_validator(mode="after")
    def validate_production_settings(self) -> "AppSettings":
        """生产环境配置验证"""
        if self.environment == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("生产环境必须禁用DEBUG模式")
            if self.security.jwt_secret_key == "change_this_in_production":
                raise ValueError("生产环境必须设置JWT_SECRET_KEY")
            if self.security.api_secret_key == "change_this_in_production":
                raise ValueError("生产环境必须设置API_SECRET_KEY")
        return self

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING


# 全局配置实例
settings = AppSettings()
