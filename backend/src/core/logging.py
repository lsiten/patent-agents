"""
结构化日志系统 - 集成 structlog
支持 JSON 格式、请求追踪、日志分级
"""
import logging
import sys
import time
import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import structlog
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from structlog.types import EventDict, Processor

from .config import settings, Environment


def add_timestamp(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """添加ISO格式时间戳"""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_service_info(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """添加服务信息"""
    event_dict["service"] = settings.app_name
    event_dict["environment"] = settings.environment.value
    event_dict["version"] = "1.0.0"
    return event_dict


def censor_secrets(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """审查并遮蔽敏感信息"""
    sensitive_keys = {
        "password", "token", "secret", "api_key", "authorization",
        "jwt", "cookie", "credential", "key"
    }

    def censor_value(value: Any) -> Any:
        if isinstance(value, str) and len(value) > 8:
            return f"{value[:4]}***{value[-4:]}"
        elif isinstance(value, str):
            return "***"
        elif isinstance(value, dict):
            return {k: censor_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [censor_value(item) for item in value]
        return value

    for key in list(event_dict.keys()):
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            event_dict[key] = censor_value(event_dict[key])
    return event_dict


class RequestIDContext:
    """请求ID上下文管理器"""
    _request_id: Optional[str] = None

    @classmethod
    def set(cls, request_id: str) -> None:
        cls._request_id = request_id

    @classmethod
    def get(cls) -> Optional[str]:
        return cls._request_id

    @classmethod
    def clear(cls) -> None:
        cls._request_id = None


def add_request_id(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """添加请求ID到日志"""
    request_id = RequestIDContext.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def get_log_processors() -> list[Processor]:
    """获取日志处理器列表"""
    shared_processors: list[Processor] = [
        add_timestamp,
        add_service_info,
        add_request_id,
        censor_secrets,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_development:
        # 开发环境：人类可读格式
        shared_processors.extend([
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    else:
        # 生产环境：JSON格式
        shared_processors.extend([
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ])

    return shared_processors


def configure_logging() -> None:
    """配置结构化日志系统"""
    # 配置标准库 logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.value),
    )

    # 配置 structlog
    structlog.configure(
        processors=get_log_processors(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 降低第三方库日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str, **bindings: Any) -> structlog.stdlib.BoundLogger:
    """获取结构化日志器"""
    return structlog.get_logger(name).bind(**bindings)


# 请求日志中间件
async def log_request_middleware(
    request: Request,
    call_next: RequestResponseEndpoint
) -> Response:
    """
    请求日志中间件
    记录请求/响应详情、耗时、状态码
    """
    # 生成或获取请求ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    RequestIDContext.set(request_id)

    start_time = time.perf_counter()
    logger = get_logger(
        "http.request",
        method=request.method,
        path=request.url.path,
        query=str(request.query_params),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )

    # 记录请求开始
    logger.info("request_started")

    try:
        response = await call_next(request)

        # 计算耗时
        duration = time.perf_counter() - start_time

        # 记录请求完成
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

        # 添加请求ID到响应头
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.error(
            "request_failed",
            duration_ms=round(duration * 1000, 2),
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=True,
        )
        raise
    finally:
        RequestIDContext.clear()


class Loggable:
    """可记录日志的基类"""

    def __init__(self, **bindings: Any) -> None:
        self._logger = get_logger(self.__class__.__name__, **bindings)

    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        return self._logger

    def log_with_context(self, level: str, message: str, **context: Any) -> None:
        """带上下文记录日志"""
        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(message, **context)
