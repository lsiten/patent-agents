"""
核心中间件
CORS、请求日志、请求ID、速率限制
"""
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .logging import log_request_middleware, get_logger

logger = get_logger(__name__)

# 速率限制器
limiter = Limiter(key_func=get_remote_address)


def register_middleware(app: FastAPI) -> None:
    """注册所有中间件"""

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # 请求日志中间件
    app.middleware("http")(log_request_middleware)

    # 请求ID中间件
    app.middleware("http")(request_id_middleware)

    # 响应时间中间件
    app.middleware("http")(response_time_middleware)

    # 注册速率限制器
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


async def request_id_middleware(request: Request, call_next):
    """请求ID中间件"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


async def response_time_middleware(request: Request, call_next):
    """响应时间中间件 - 添加X-Response-Time头"""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Response-Time"] = f"{process_time:.3f}"
    return response


# ========== 速率限制依赖 ==========

def rate_limit(limit: str = "100/minute"):
    """
    速率限制装饰器
    使用方式:
        @app.get("/api/chat")
        @rate_limit("50/minute")
        async def chat_endpoint():
            ...
    """
    return limiter.limit(limit)


# ========== SSE 连接管理 ==========

class SSEConnectionManager:
    """SSE连接管理器 - 管理实时事件推送连接"""

    def __init__(self):
        self.active_connections: dict[str, list] = {}  # user_id -> connections
        self._logger = get_logger("sse_manager")

    async def connect(self, user_id: str, connection):
        """建立连接"""
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(connection)
        self._logger.info("SSE connection established", user_id=user_id, total_connections=len(self.active_connections))

    def disconnect(self, user_id: str, connection):
        """断开连接"""
        if user_id in self.active_connections:
            if connection in self.active_connections[user_id]:
                self.active_connections[user_id].remove(connection)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        self._logger.info("SSE connection closed", user_id=user_id, total_connections=len(self.active_connections))

    async def send_event(self, user_id: str, event: str, data: dict):
        """向指定用户发送事件"""
        if user_id not in self.active_connections:
            return

        message = f"event: {event}\ndata: {data}\n\n"
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                self._logger.warning("Failed to send SSE event", user_id=user_id, error=str(e))

    async def broadcast(self, event: str, data: dict):
        """向所有连接广播事件"""
        for user_id in list(self.active_connections.keys()):
            await self.send_event(user_id, event, data)


# 全局SSE管理器
sse_manager = SSEConnectionManager()
