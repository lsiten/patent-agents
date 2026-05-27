"""
Simple JSON key-value store for persisting in-memory stores (tasks, conversations, events).
Bridges the gap between Pydantic domain models (used by agents) and SQLAlchemy.
"""
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import String, JSON, DateTime, func, select, delete
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StoredValue(Base):
    """Generic key-value-category store with JSON value column."""
    __tablename__ = "stored_values"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
