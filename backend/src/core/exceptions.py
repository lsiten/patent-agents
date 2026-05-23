"""
异常处理框架
自定义异常类、错误码定义、全局异常处理器
"""
from enum import Enum
from typing import Any, Dict, Optional, Union
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from .logging import get_logger

logger = get_logger(__name__)


class ErrorCode(str, Enum):
    """错误码枚举"""
    # 系统级错误 (1000-1999)
    INTERNAL_ERROR = "SYS_1000"
    SERVICE_UNAVAILABLE = "SYS_1001"
    DATABASE_ERROR = "SYS_1002"
    CACHE_ERROR = "SYS_1003"
    TIMEOUT_ERROR = "SYS_1004"
    RATE_LIMIT_EXCEEDED = "SYS_1005"

    # 请求验证错误 (3000-3999)
    VALIDATION_ERROR = "REQ_3000"
    MISSING_PARAMETER = "REQ_3001"
    INVALID_PARAMETER = "REQ_3002"
    UNSUPPORTED_FORMAT = "REQ_3003"
    FILE_TOO_LARGE = "REQ_3004"

    # 业务逻辑错误 (4000-4999)
    RESOURCE_NOT_FOUND = "BIZ_4000"
    RESOURCE_CONFLICT = "BIZ_4001"
    RESOURCE_ALREADY_EXISTS = "BIZ_4002"
    INVALID_STATE_TRANSITION = "BIZ_4003"
    BUSINESS_RULE_VIOLATION = "BIZ_4004"
    OPERATION_NOT_ALLOWED = "BIZ_4005"

    # Agent 相关错误 (5000-5999)
    AGENT_ERROR = "AGENT_5000"
    AGENT_TIMEOUT = "AGENT_5001"
    AGENT_NOT_FOUND = "AGENT_5002"
    LLM_API_ERROR = "AGENT_5003"
    PROMPT_TOO_LONG = "AGENT_5004"
    INVALID_AGENT_CONFIG = "AGENT_5005"

    # 工作流相关错误 (6000-6999)
    WORKFLOW_ERROR = "WF_6000"
    WORKFLOW_TIMEOUT = "WF_6001"
    WORKFLOW_ALREADY_RUNNING = "WF_6002"
    WORKFLOW_NOT_FOUND = "WF_6003"
    TASK_CANCELLED = "WF_6004"
    ITERATION_LIMIT_EXCEEDED = "WF_6005"

    # 专利相关错误 (7000-7999)
    PATENT_ERROR = "PAT_7000"
    PATENT_NOT_FOUND = "PAT_7001"
    PATENT_DATA_ERROR = "PAT_7002"
    EXPORT_ERROR = "PAT_7003"
    PATENT_DB_CONNECTION_FAILED = "PAT_7004"


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorDetail(BaseModel):
    """错误详情模型"""
    code: ErrorCode
    message: str
    severity: ErrorSeverity
    details: Dict[str, Any] = {}
    timestamp: str = ""
    request_id: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class BaseAppException(Exception):
    """应用基础异常类"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.code = code
        self.message = message
        self.severity = severity
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)

    def to_detail(self, request_id: Optional[str] = None) -> ErrorDetail:
        return ErrorDetail(
            code=self.code,
            message=self.message,
            severity=self.severity,
            details=self.details,
            request_id=request_id,
        )


# ========== 系统异常 ==========

class InternalError(BaseAppException):
    """内部系统错误"""
    def __init__(
        self,
        message: str = "内部服务错误",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DatabaseError(BaseAppException):
    """数据库错误"""
    def __init__(
        self,
        message: str = "数据库操作失败",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.DATABASE_ERROR,
            message=message,
            severity=ErrorSeverity.HIGH,
            details=details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class TimeoutError(BaseAppException):
    """超时错误"""
    def __init__(
        self,
        message: str = "操作超时",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.TIMEOUT_ERROR,
            message=message,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class RateLimitExceeded(BaseAppException):
    """速率限制超限"""
    def __init__(
        self,
        message: str = "请求频率超限，请稍后再试",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=message,
            severity=ErrorSeverity.LOW,
            details=details,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


# ========== 业务异常 ==========

class ResourceNotFoundError(BaseAppException):
    """资源未找到"""
    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"{resource_type}未找到"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            message=message,
            severity=ErrorSeverity.LOW,
            details=details or {"resource_type": resource_type, "resource_id": resource_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ResourceAlreadyExistsError(BaseAppException):
    """资源已存在"""
    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"{resource_type}已存在"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(
            code=ErrorCode.RESOURCE_ALREADY_EXISTS,
            message=message,
            severity=ErrorSeverity.LOW,
            details=details or {"resource_type": resource_type, "resource_id": resource_id},
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidStateTransitionError(BaseAppException):
    """无效状态转换"""
    def __init__(
        self,
        from_state: str,
        to_state: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message=f"无效的状态转换: {from_state} -> {to_state}",
            severity=ErrorSeverity.MEDIUM,
            details=details or {"from_state": from_state, "to_state": to_state},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class BusinessRuleViolationError(BaseAppException):
    """业务规则违反"""
    def __init__(
        self,
        message: str,
        rule: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        full_details = details or {}
        full_details["rule"] = rule
        super().__init__(
            code=ErrorCode.BUSINESS_RULE_VIOLATION,
            message=message,
            severity=ErrorSeverity.MEDIUM,
            details=full_details,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


# ========== Agent 异常 ==========

class AgentError(BaseAppException):
    """Agent执行错误"""
    def __init__(
        self,
        agent_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.AGENT_ERROR,
            message=f"Agent [{agent_name}] 执行失败: {message}",
            severity=ErrorSeverity.HIGH,
            details=details or {"agent_name": agent_name},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class AgentTimeoutError(BaseAppException):
    """Agent超时"""
    def __init__(
        self,
        agent_name: str,
        timeout_seconds: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.AGENT_TIMEOUT,
            message=f"Agent [{agent_name}] 执行超时（{timeout_seconds}秒）",
            severity=ErrorSeverity.MEDIUM,
            details=details or {"agent_name": agent_name, "timeout_seconds": timeout_seconds},
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class LLMAPIError(BaseAppException):
    """LLM API错误"""
    def __init__(
        self,
        provider: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.LLM_API_ERROR,
            message=f"{provider} API调用失败: {message}",
            severity=ErrorSeverity.HIGH,
            details=details or {"provider": provider},
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


# ========== 工作流异常 ==========

class WorkflowTimeoutError(BaseAppException):
    """工作流超时"""
    def __init__(
        self,
        task_id: str,
        timeout_seconds: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.WORKFLOW_TIMEOUT,
            message=f"任务 [{task_id}] 执行超时（{timeout_seconds}秒）",
            severity=ErrorSeverity.HIGH,
            details=details or {"task_id": task_id, "timeout_seconds": timeout_seconds},
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class WorkflowNotFoundError(BaseAppException):
    """工作流未找到"""
    def __init__(
        self,
        task_id: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.WORKFLOW_NOT_FOUND,
            message=f"任务 [{task_id}] 不存在",
            severity=ErrorSeverity.LOW,
            details=details or {"task_id": task_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )


class TaskCancelledError(BaseAppException):
    """任务已取消"""
    def __init__(
        self,
        task_id: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.TASK_CANCELLED,
            message=f"任务 [{task_id}] 已被取消",
            severity=ErrorSeverity.MEDIUM,
            details=details or {"task_id": task_id},
            status_code=status.HTTP_409_CONFLICT,
        )


class IterationLimitExceededError(BaseAppException):
    """迭代次数超限"""
    def __init__(
        self,
        max_iterations: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.ITERATION_LIMIT_EXCEEDED,
            message=f"已达到最大迭代次数限制: {max_iterations}",
            severity=ErrorSeverity.MEDIUM,
            details=details or {"max_iterations": max_iterations},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


# ========== 全局异常处理器 ==========

def _add_cors_headers(response: JSONResponse, request: Request) -> JSONResponse:
    """为错误响应添加 CORS 头，确保浏览器能读取错误信息"""
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = (
            "X-Request-ID, X-RateLimit-Limit, X-RateLimit-Remaining"
        )
        response.headers["Vary"] = "Origin"
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(BaseAppException)
    async def handle_app_exception(
        request: Request,
        exc: BaseAppException
    ) -> JSONResponse:
        """处理应用自定义异常"""
        request_id = getattr(request.state, "request_id", None)
        error_detail = exc.to_detail(request_id=request_id)

        # 根据严重级别记录日志
        log_level = {
            ErrorSeverity.LOW: "debug",
            ErrorSeverity.MEDIUM: "info",
            ErrorSeverity.HIGH: "warning",
            ErrorSeverity.CRITICAL: "error",
        }.get(exc.severity, "error")

        getattr(logger, log_level)(
            exc.message,
            code=exc.code.value,
            details=exc.details,
            status_code=exc.status_code,
            path=str(request.url),
            method=request.method,
        )

        return _add_cors_headers(
            JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "error": error_detail.model_dump(),
                },
            ),
            request,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(
        request: Request,
        exc: SQLAlchemyError
    ) -> JSONResponse:
        """处理数据库异常"""
        logger.error(
            "Database error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=str(request.url),
            method=request.method,
        )

        db_error = DatabaseError(details={"error_type": type(exc).__name__})
        return _add_cors_headers(
            JSONResponse(
                status_code=db_error.status_code,
                content={
                    "success": False,
                    "error": db_error.to_detail().model_dump(),
                },
            ),
            request,
        )

    @app.exception_handler(status.HTTP_422_UNPROCESSABLE_ENTITY)
    async def handle_validation_error(
        request: Request,
        exc: Any
    ) -> JSONResponse:
        """处理验证错误"""
        from fastapi.exceptions import RequestValidationError

        if isinstance(exc, RequestValidationError):
            details = {"errors": exc.errors()}
            logger.warning(
                "Validation error",
                errors=exc.errors(),
                path=str(request.url),
                method=request.method,
            )
        else:
            details = {}
            logger.warning(
                "Validation error",
                error=str(exc),
                path=str(request.url),
                method=request.method,
            )

        error_detail = ErrorDetail(
            code=ErrorCode.VALIDATION_ERROR,
            message="请求参数验证失败",
            severity=ErrorSeverity.LOW,
            details=details,
        )

        return _add_cors_headers(
            JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "success": False,
                    "error": error_detail.model_dump(),
                },
            ),
            request,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """处理未预期的异常"""
        logger.critical(
            "Unhandled exception",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=str(request.url),
            method=request.method,
            exc_info=True,
        )

        internal_error = InternalError(
            details={"error_type": type(exc).__name__}
        )
        return _add_cors_headers(
            JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "error": internal_error.to_detail().model_dump(),
                },
            ),
            request,
        )
