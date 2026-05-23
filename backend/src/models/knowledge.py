"""
Knowledge base ORM models (patent knowledge, vector search)
"""
from typing import Optional
from sqlalchemy import String, Text, Date, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class KnowledgePatent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_patents"

    patent_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    application_number: Mapped[Optional[str]] = mapped_column(String(64))
    publication_number: Mapped[Optional[str]] = mapped_column(String(64))
    applicant: Mapped[Optional[str]] = mapped_column(String(500))
    inventor: Mapped[Optional[str]] = mapped_column(String(500))
    application_date: Mapped[Optional[str]] = mapped_column()
    publication_date: Mapped[Optional[str]] = mapped_column()
    ipc_codes: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    cpc_codes: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    country_code: Mapped[Optional[str]] = mapped_column(String(8))
    status: Mapped[Optional[str]] = mapped_column(String(32))
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    source: Mapped[Optional[str]] = mapped_column(String(32))
