#!/usr/bin/env python3
"""
专利申请多智能体系统 - 后端入口
"""
import asyncio
import uvicorn
from fastapi import FastAPI

from src.core import (
    settings,
    configure_logging,
    get_logger,
    init_container,
    cleanup_container,
    register_middleware,
    register_exception_handlers,
    init_event_bus,
    container,
)
from src.api.routes import router as api_router

# 配置日志
configure_logging()
logger = get_logger(__name__)

# 初始化FastAPI应用
app = FastAPI(
    title="专利智脑 - AI驱动的专利申请多智能体系统",
    description="基于CEO Agent统筹的分层多智能体架构，自动化完成专利申请全流程",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    root_path=settings.root_path,
)

# 注册中间件
register_middleware(app)

# 注册异常处理器
register_exception_handlers(app)

# 注册API路由
app.include_router(api_router, prefix=settings.api_version)


# 启动事件
@app.on_event("startup")
async def startup_event():
    logger.info("正在启动专利智脑服务...", environment=settings.environment.value)

    try:
        # 初始化依赖注入容器
        await init_container()

        # 初始化事件总线
        # container.redis_client is a Factory(redis_provider.provided.get_client)
        # — calling it returns the bound get_client method, not the client value itself.
        # Double-call to resolve: first gets the method, second invokes it.
        redis_client = container.redis_client()()
        await init_event_bus(redis_client)

        # 初始化持久化存储（用于在 DB 中持久化内存 store）
        from src.infrastructure.persistence import init_store
        init_store(container.db_provider().async_session_factory)
        logger.info("持久化存储初始化完成")

        # 从数据库恢复内存存储（使已持久化的数据在重启后可用）
        from src.api.routes import restore_stores_from_db
        await restore_stores_from_db()

        # Hermes 专利工具由 hermes_agent_service 按需注册（lazy init）
        logger.info("专利智脑服务启动成功!", port=settings.port)

    except Exception as e:
        logger.critical("服务启动失败", error=str(e), exc_info=True)
        raise


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("专利智脑服务正在关闭...")

    try:
        # 清理容器资源
        await cleanup_container()
        logger.info("资源清理完成")
    except Exception as e:
        logger.error("关闭过程中出错", error=str(e))

    logger.info("专利智脑服务已关闭")


# 根路径
@app.get("/")
async def root():
    return {
        "name": "专利智脑 - AI驱动的专利申请多智能体系统",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.environment.value,
        "docs": "/docs" if not settings.is_production else None,
        "api_base": settings.api_version,
    }


# 健康检查
@app.get("/health")
async def health_check_endpoint():
    return {
        "status": "healthy",
        "timestamp": settings.db.url,
        "environment": settings.environment.value,
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.value.lower(),
        workers=1 if settings.is_development else 4,
    )
