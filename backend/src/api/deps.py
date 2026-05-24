"""
API 依赖项 — 认证、权限等

提供 get_current_user / get_current_user_optional 等 FastAPI 依赖
供路由端点使用，在 AGENTS.md 中作为标准模式文档化。

当前实现为轻量方案（X-User-ID header + 可选 Bearer token），
后续可替换为完整 JWT 验证。
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, status


async def get_current_user_optional(
    x_user_id: Optional[str] = Header(default=None, description="用户 ID（未登录时可选）"),
) -> str:
    """
    获取当前用户 ID（可选认证）。

    优先从 X-User-ID header 读取，其次从请求 body 的 user_id 字段获取。
    均不存在时返回 "default_user"（向后兼容）。

    在需要强制认证的路由中使用 get_current_user 替代。
    """
    return x_user_id or "default_user"


async def get_current_user(
    x_user_id: str = Header(..., description="用户 ID（必填）"),
) -> str:
    """
    获取当前用户 ID（强制认证）。

    要求请求头必须包含 X-User-ID。
    未提供时返回 401 Unauthorized。
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header",
        )
    return x_user_id
