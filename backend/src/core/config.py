"""
项目配置系统 - 使用 Pydantic Settings 实现
支持环境变量、.env 文件、配置验证
"""
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

_backend_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_selected_env_file = os.getenv("PATENT_AGENTS_ENV_FILE")

# 显式加载 .env 文件到 os.environ，确保嵌套模型也能读取环境变量。
if _selected_env_file:
    _selected_env_path = os.path.abspath(_selected_env_file)
    if not os.path.isfile(_selected_env_path):
        raise RuntimeError(f"PATENT_AGENTS_ENV_FILE does not exist: {_selected_env_path}")
    load_dotenv(_selected_env_path, override=True)
else:
    _env_path = os.path.join(_backend_root, ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)

    if os.getenv("ENVIRONMENT") == "testing":
        _test_env_path = os.path.join(_backend_root, ".env.testing")
        if os.path.isfile(_test_env_path):
            load_dotenv(_test_env_path, override=True)

    if os.getenv("ENVIRONMENT") == "production":
        _prod_env_path = os.path.join(_backend_root, ".env.production")
        if os.path.isfile(_prod_env_path):
            load_dotenv(_prod_env_path, override=True)


class Environment(str, Enum):
    """运行环境枚举"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# ── 所有已知供应商列表（用于校验等） ──
TEXT_LLM_PROVIDERS = {"openai", "anthropic"}
IMAGE_GEN_PROVIDERS = {"azure_aoai", "openai"}


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
    """文字 LLM API 配置 — 统一命名: LLM_{PROVIDER}_{FIELD}"""

    # 当前激活的供应商
    active_provider: str = Field(
        default="openai", alias="LLM_ACTIVE_PROVIDER"
    )

    # ── OpenAI / 兼容代理 ──
    openai_api_key: Optional[str] = Field(default=None, alias="LLM_OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="LLM_OPENAI_BASE_URL"
    )
    openai_model: str = Field(default="gpt-4-turbo-preview", alias="LLM_OPENAI_MODEL")

    # ── Anthropic Claude ──
    anthropic_api_key: Optional[str] = Field(default=None, alias="LLM_ANTHROPIC_API_KEY")
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1",
        alias="LLM_ANTHROPIC_BASE_URL"
    )
    anthropic_model: str = Field(
        default="claude-3-opus-20240229", alias="LLM_ANTHROPIC_MODEL"
    )

    # ── DeepSeek ──
    deepseek_api_key: Optional[str] = Field(default=None, alias="LLM_DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        alias="LLM_DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(default="deepseek-chat", alias="LLM_DEEPSEEK_MODEL")

    # ── OpenRouter ──
    openrouter_api_key: Optional[str] = Field(default=None, alias="LLM_OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="LLM_OPENROUTER_BASE_URL",
    )
    openrouter_model: str = Field(default="openrouter/auto", alias="LLM_OPENROUTER_MODEL")

    # ── API 模式（覆盖自动检测） ──
    api_mode: Optional[str] = Field(
        default=None, alias="LLM_API_MODE",
        description="强制指定 API 模式，覆盖自动检测",
    )

    # 通用配置
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="LLM_TEMPERATURE")
    max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    timeout: int = Field(default=120, description="LLM请求超时(秒)", alias="LLM_TIMEOUT")
    enable_fallback: bool = Field(default=True, description="启用LLM降级策略")
    fallback_order: List[str] = Field(
        default_factory=lambda: ["openai", "anthropic"]
    )
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟(秒)")

    model_config = {"extra": "ignore"}

    def get_provider_config(self, provider: Optional[str] = None) -> dict:
        """获取指定供应商（或当前激活供应商）的连接配置"""
        p = provider or self.active_provider
        if p not in TEXT_LLM_PROVIDERS:
            p = "openai"
        return {
            "base_url": getattr(self, f"{p}_base_url", None),
            "api_key": getattr(self, f"{p}_api_key", None),
            "model_id": getattr(self, f"{p}_model", None),
        }

    def resolve_for_agent(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        解析指定 agent 的最终 LLM 配置。

        合并策略：agent 覆盖 > 全局 active provider。
        overrides 允许的字段：
            - provider: 供应商名（不在白名单时回退 active_provider）
            - base_url: 自定义 base URL
            - api_key:  明文或 "enc:..." 加密值
            - model:    模型 ID
        缺失字段从全局同 provider 配置补齐。

        返回 dict 形如 {"provider", "base_url", "api_key", "model_id"}。
        """
        from .secret_cipher import decrypt_value

        overrides = overrides or {}

        requested_provider = overrides.get("provider")
        if requested_provider and requested_provider in TEXT_LLM_PROVIDERS:
            provider = requested_provider
        else:
            provider = self.active_provider

        base = self.get_provider_config(provider)

        if "base_url" in overrides and overrides["base_url"] is not None:
            base["base_url"] = overrides["base_url"]
        if "api_key" in overrides and overrides["api_key"] is not None:
            base["api_key"] = decrypt_value(overrides["api_key"])
        if "model" in overrides and overrides["model"] is not None:
            base["model_id"] = overrides["model"]

        base["provider"] = provider
        return base

    @field_validator("fallback_order")
    @classmethod
    def validate_fallback_order(cls, v: List[str]) -> List[str]:
        if not all(p in TEXT_LLM_PROVIDERS for p in v):
            raise ValueError(f"Fallback providers must be one of {TEXT_LLM_PROVIDERS}")
        return v


class ImageGenSettings(BaseSettings):
    """生图 API 配置 — 支持多供应商，base_url / api_key / model_id 三元组"""

    # 当前激活的供应商
    active_provider: str = Field(
        default="azure_aoai", alias="IMAGE_GEN_ACTIVE_PROVIDER",
    )

    # ── Azure OpenAI (default, intsig proxy for gpt-image-2) ──
    azure_aoai_base_url: str = Field(
        default="http://deepseek-work.intsig.net/proxy/azure/gpt/v1",
        alias="IMAGE_GEN_AZURE_AOAI_BASE_URL",
    )
    azure_aoai_api_key: Optional[str] = Field(
        default=None, alias="IMAGE_GEN_AZURE_AOAI_API_KEY",
    )
    azure_aoai_model_id: str = Field(
        default="gpt-image-2", alias="IMAGE_GEN_AZURE_AOAI_MODEL_ID",
    )

    # ── OpenAI (DALL-E) ──
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="IMAGE_GEN_OPENAI_BASE_URL",
    )
    openai_api_key: Optional[str] = Field(
        default=None, alias="IMAGE_GEN_OPENAI_API_KEY",
    )
    openai_model_id: str = Field(
        default="dall-e-3", alias="IMAGE_GEN_OPENAI_MODEL_ID",
    )

    # ── Stability AI (Stable Diffusion) ──
    stability_base_url: str = Field(
        default="https://api.stability.ai/v1",
        alias="IMAGE_GEN_STABILITY_BASE_URL",
    )
    stability_api_key: Optional[str] = Field(
        default=None, alias="IMAGE_GEN_STABILITY_API_KEY",
    )
    stability_model_id: str = Field(
        default="stable-diffusion-3", alias="IMAGE_GEN_STABILITY_MODEL_ID",
    )

    model_config = {"env_prefix": "IMAGE_GEN_"}

    def get_provider_config(
        self, provider: Optional[str] = None,
    ) -> dict:
        """获取指定供应商（或当前激活供应商）的连接配置"""
        p = provider or self.active_provider
        if p not in IMAGE_GEN_PROVIDERS:
            p = "azure_aoai"
        return {
            "base_url": getattr(self, f"{p}_base_url", None),
            "api_key": getattr(self, f"{p}_api_key", None),
            "model_id": getattr(self, f"{p}_model_id", None),
        }

    def is_configured(self) -> bool:
        """是否有至少一个供应商配置了 API key"""
        for p in IMAGE_GEN_PROVIDERS:
            if getattr(self, f"{p}_api_key", None):
                return True
        return False

    def resolve_for_agent(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        解析指定 agent 的最终生图配置。

        合并策略同 LLMSettings.resolve_for_agent，但 override 字段名为 `model_id`
        （区别于 LLM 的 `model`）。
        """
        from .secret_cipher import decrypt_value

        overrides = overrides or {}

        requested_provider = overrides.get("provider")
        if requested_provider and requested_provider in IMAGE_GEN_PROVIDERS:
            provider = requested_provider
        else:
            provider = self.active_provider

        base = self.get_provider_config(provider)

        if "base_url" in overrides and overrides["base_url"] is not None:
            base["base_url"] = overrides["base_url"]
        if "api_key" in overrides and overrides["api_key"] is not None:
            base["api_key"] = decrypt_value(overrides["api_key"])
        if "model_id" in overrides and overrides["model_id"] is not None:
            base["model_id"] = overrides["model_id"]

        base["provider"] = provider
        return base

    def resolve_config(
        self, llm_settings: "LLMSettings",
    ) -> dict:
        """
        解析最终的生图配置。
        生图已配置 → 返回生图配置
        生图未配置 → 回退到文字 LLM 配置（base_url + api_key + 默认图片模型 ID）
        """
        if self.is_configured():
            return self.get_provider_config()
        # Fallback: 用文字 LLM 当前激活的供应商
        llm_provider = llm_settings.get_provider_config()
        llm_base_url = llm_provider.get("base_url") or ""
        # OpenAI-compatible base url → 拼接 /images/generations 路径
        return {
            "base_url": llm_base_url,
            "api_key": llm_provider.get("api_key"),
            "model_id": "gpt-image-2",  # 回退时的默认图片模型
        }


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
        alias="ENVIRONMENT",
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
    image_gen: ImageGenSettings = Field(default_factory=ImageGenSettings)
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

    @model_validator(mode="after")
    def resolve_environment_isolation(self) -> "AppSettings":
        if self.environment == Environment.PRODUCTION:
            self.db.url = "sqlite+aiosqlite:///./prod_patent_agents.db"
            self.storage.knowledge_base_path = "./prod_finalized_patents"
            self.storage.export_path = "./prod_exports"
            self.storage.finalized_patents_docx_path = "./prod_定稿文件"
        elif self.environment == Environment.TESTING:
            self.db.url = "sqlite+aiosqlite:///./test_patent_agents.db"
            self.storage.knowledge_base_path = "./test_finalized_patents"
            self.storage.export_path = "./test_exports"
            self.storage.finalized_patents_docx_path = "./test_定稿文件"
            self.debug = False
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


def reload_settings() -> None:
    """
    运行时重新加载配置（不重启服务）。

    调用时机：
    - 用户在 system-config 页面保存新配置后
    - `.env` 文件已被外部写入后

    工作原理：
    1. 重读 `.env` 文件并覆盖到 os.environ（确保新建进程/线程也能拿到新值）
    2. 创建全新的 AppSettings 实例
    3. 将全部字段逐个 setattr 到全局 settings 对象上

    由于 Python 属性访问是运行时动态的，所有 import 了 settings 的模块
    （from config import settings）都能立即读取到新值。
    """
    from dotenv import load_dotenv

    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.isfile(env_path):
        load_dotenv(env_path, override=True)

    fresh = AppSettings()
    for field_name in settings.model_fields:
        setattr(settings, field_name, getattr(fresh, field_name))
