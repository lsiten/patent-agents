"""
Agent + tool + skill + memory ORM models
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, UniqueConstraint, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


class Agent(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "agents"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)  # orchestrator, specialist, assistant
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="gpt-4-turbo")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    top_p: Mapped[float] = mapped_column(Float, default=1.0)
    frequency_penalty: Mapped[float] = mapped_column(Float, default=0)
    presence_penalty: Mapped[float] = mapped_column(Float, default=0)
    working_directory: Mapped[Optional[str]] = mapped_column(String(512))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uc_agent_org_name"),
    )

    organization = relationship("Organization", back_populates="agents")
    tools = relationship("AgentTool", back_populates="agent", lazy="selectin",
                         cascade="all, delete-orphan")
    skills = relationship("AgentSkill", back_populates="agent", lazy="selectin",
                          cascade="all, delete-orphan")
    memories = relationship("AgentMemory", back_populates="agent", lazy="selectin",
                            cascade="all, delete-orphan")


class AgentTool(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_tools"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_json: Mapped[Optional[dict]] = mapped_column(JSON)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uc_agent_tool_name"),
    )

    agent = relationship("Agent", back_populates="tools")


class AgentSkill(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    skill_type: Mapped[Optional[str]] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    prompt_template: Mapped[Optional[str]] = mapped_column(Text)
    examples: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uc_agent_skill_name"),
    )

    agent = relationship("Agent", back_populates="skills")


class AgentMemory(UUIDMixin, Base):
    __tablename__ = "agent_memories"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column()
    expires_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[Optional[datetime]] = mapped_column()

    agent = relationship("Agent", back_populates="memories")
