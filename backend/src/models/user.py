"""
User ORM Model
"""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from .patent import PatentTask


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """用户表"""
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(50), default="user")

    # relationships
    tasks: Mapped[List["PatentTask"]] = relationship("PatentTask", back_populates="user", lazy="selectin")
