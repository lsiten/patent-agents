"""
Chat session + message ORM models
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


class ChatSession(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id")
    )
    title: Mapped[Optional[str]] = mapped_column(String(500))
    session_type: Mapped[str] = mapped_column(String(32), default="general")
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    last_message_at: Mapped[Optional[str]] = mapped_column()

    messages = relationship("ChatMessage", back_populates="session", lazy="selectin",
                            cascade="all, delete-orphan")


class ChatMessage(UUIDMixin, SoftDeleteMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id")
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user, assistant, system, agent
    agent_name: Mapped[Optional[str]] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[str]] = mapped_column()

    session = relationship("ChatSession", back_populates="messages")
