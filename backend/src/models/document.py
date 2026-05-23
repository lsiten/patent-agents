"""
Patent document ORM models (requirement, retrieval, draft, review, final)
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean, BigInteger, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin


class RequirementDoc(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "requirement_docs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    tech_field: Mapped[Optional[str]] = mapped_column(String(200))
    core_principle: Mapped[Optional[str]] = mapped_column(Text)
    technical_problem: Mapped[Optional[str]] = mapped_column(Text)
    application_scenarios: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    key_features: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    patent_type_recommendation: Mapped[Optional[dict]] = mapped_column(JSON)
    beneficial_effects: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    information_gaps: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    raw_output: Mapped[Optional[str]] = mapped_column(Text)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    task = relationship("PatentTask", back_populates="requirement_doc")


class RetrievalReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_reports"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    novelty_assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    inventive_step_assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    utility_assessment: Mapped[dict] = mapped_column(JSON, nullable=False)
    similar_patents: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    writing_recommendations: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    overall_patentability: Mapped[str] = mapped_column(String(16), default="medium")
    overall_score: Mapped[Optional[float]] = mapped_column()
    risk_factors: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    search_criteria: Mapped[Optional[dict]] = mapped_column(JSON)
    data_sources: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    raw_output: Mapped[Optional[str]] = mapped_column(Text)

    task = relationship("PatentTask", back_populates="retrieval_report")


class PatentDraft(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "patent_drafts"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    claims: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[dict] = mapped_column(JSON, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    technical_field: Mapped[Optional[str]] = mapped_column(Text)
    background_art: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    description_drawings: Mapped[Optional[str]] = mapped_column(Text)
    detailed_description: Mapped[Optional[str]] = mapped_column(Text)
    drawings: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    key_terms: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    raw_output: Mapped[Optional[str]] = mapped_column(Text)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    task = relationship("PatentTask", back_populates="patent_draft")


class ReviewReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "review_reports"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    formal_compliance: Mapped[dict] = mapped_column(JSON, nullable=False)
    claims_review: Mapped[dict] = mapped_column(JSON, nullable=False)
    description_review: Mapped[dict] = mapped_column(JSON, nullable=False)
    consistency_review: Mapped[dict] = mapped_column(JSON, nullable=False)
    examination_risks: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    overall_score: Mapped[Optional[float]] = mapped_column()
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    revision_priority: Mapped[Optional[str]] = mapped_column(String(16))
    issues: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    suggestions: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    raw_output: Mapped[Optional[str]] = mapped_column(Text)

    task = relationship("PatentTask", back_populates="review_report")


class FinalPatent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "final_patents"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    claims: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[dict] = mapped_column(JSON, nullable=False)
    drawings: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    file_urls: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    format_versions: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[Optional[str]] = mapped_column()
    submission_reference: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="generated")

    task = relationship("PatentTask", back_populates="final_patent")


class Document(UUIDMixin, Base):
    __tablename__ = "documents"

    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patent_tasks.id")
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    md5_hash: Mapped[Optional[str]] = mapped_column(String(32))
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[Optional[str]] = mapped_column()
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
