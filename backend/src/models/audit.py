"""
Audit + API usage ORM models
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, ForeignKey, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64))
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    old_values: Mapped[Optional[dict]] = mapped_column(JSON)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[Optional[str]] = mapped_column()


class ApiUsage(UUIDMixin, Base):
    __tablename__ = "api_usage"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(255))
    method: Mapped[Optional[str]] = mapped_column(String(16))
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_amount: Mapped[Optional[float]] = mapped_column(Float)
    cost_currency: Mapped[str] = mapped_column(String(8), default="USD")
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[Optional[str]] = mapped_column()
