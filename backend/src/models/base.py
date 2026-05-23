"""
SQLAlchemy ORM 基类 — DeclarativeBase + 通用 Mixin
"""
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, Boolean, func, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """创建/更新时间戳 Mixin"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """软删除 Mixin"""
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UUIDMixin:
    """UUID 主键 Mixin"""
    id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
