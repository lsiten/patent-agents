"""
Simple JSON key-value persistence for in-memory stores.
Used by routes.py to persist PatentTask (Pydantic) and conversations to DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.store import StoredValue


_category_prefix: str = ""

def set_category_prefix(prefix: str) -> None:
    global _category_prefix
    _category_prefix = prefix


def _cat(name: str) -> str:
    return f"{_category_prefix}:{name}" if _category_prefix else name


class StoreManager:
    """Generic JSON-backed key-value store.

    Categories: ``tasks``, ``task_events``, ``conversations``
    Each key within a category maps to a JSON value.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def save(self, category: str, key: str, value: Any) -> None:
        cat = _cat(category)
        async with self._sf() as session:
            stmt = select(StoredValue).where(
                StoredValue.key == key, StoredValue.category == cat
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                row.value = value
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return

            session.add(StoredValue(key=key, category=cat, value=value))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if not row:
                    raise
                row.value = value
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def load(self, category: str, key: str) -> Optional[Any]:
        cat = _cat(category)
        async with self._sf() as session:
            stmt = select(StoredValue).where(
                StoredValue.key == key, StoredValue.category == cat
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row.value if row else None

    async def load_all(self, category: str) -> list[tuple[str, Any]]:
        cat = _cat(category)
        async with self._sf() as session:
            stmt = (
                select(StoredValue)
                .where(StoredValue.category == cat)
                .order_by(StoredValue.created_at)
            )
            result = await session.execute(stmt)
            return [(r.key, r.value) for r in result.scalars().all()]

    async def delete(self, category: str, key: str) -> None:
        cat = _cat(category)
        async with self._sf() as session:
            stmt = delete(StoredValue).where(
                StoredValue.key == key, StoredValue.category == cat
            )
            await session.execute(stmt)
            await session.commit()

    async def count(self, category: str) -> int:
        cat = _cat(category)
        async with self._sf() as session:
            stmt = (
                select(StoredValue)
                .where(StoredValue.category == cat)
            )
            result = await session.execute(stmt)
            return len(list(result.scalars().all()))


# ── Module-level helpers (lazily bound to container session factory) ──

_manager: Optional[StoreManager] = None


def init_store(session_factory: async_sessionmaker[AsyncSession]) -> StoreManager:
    global _manager
    _manager = StoreManager(session_factory)
    return _manager


def get_store() -> StoreManager:
    assert _manager is not None, "StoreManager not initialized — call init_store() first"
    return _manager
