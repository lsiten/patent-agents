"""
Organization ORM Model
"""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from .agent import Agent


class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """组织/团队表"""
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # relationships
    agents: Mapped[List["Agent"]] = relationship("Agent", back_populates="organization", lazy="selectin")
