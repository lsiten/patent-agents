"""
Patent task + event ORM models
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, SmallInteger, Integer, ForeignKey, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


class PatentTask(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "patent_tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tech_description: Mapped[str] = mapped_column(Text, nullable=False)
    patent_type: Mapped[str] = mapped_column(String(32), default="invention")
    current_state: Mapped[str] = mapped_column(String(32), default="initial", index=True)
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[str]] = mapped_column()
    completed_at: Mapped[Optional[str]] = mapped_column()

    # relationships
    user = relationship("User", back_populates="tasks")
    events = relationship("TaskEvent", back_populates="task", lazy="selectin",
                          cascade="all, delete-orphan")
    requirement_doc = relationship("RequirementDoc", back_populates="task", uselist=False,
                                    cascade="all, delete-orphan")
    retrieval_report = relationship("RetrievalReport", back_populates="task", uselist=False,
                                     cascade="all, delete-orphan")
    patent_draft = relationship("PatentDraft", back_populates="task", uselist=False,
                                cascade="all, delete-orphan")
    review_report = relationship("ReviewReport", back_populates="task", uselist=False,
                                 cascade="all, delete-orphan")
    final_patent = relationship("FinalPatent", back_populates="task", uselist=False,
                                cascade="all, delete-orphan")


class TaskEvent(UUIDMixin, Base):
    __tablename__ = "task_events"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[Optional[str]] = mapped_column()

    # relationships
    task = relationship("PatentTask", back_populates="events")
