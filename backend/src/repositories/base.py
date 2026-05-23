from __future__ import annotations
import uuid
from typing import Generic, TypeVar, Any, Sequence
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic SQLAlchemy async repository with CRUD + soft-delete."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, offset: int = 0, limit: int = 100, **filters: Any
    ) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        for attr, value in filters.items():
            if hasattr(self.model, attr) and value is not None:
                stmt = stmt.where(getattr(self.model, attr) == value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_all(self, entities: list[ModelT]) -> list[ModelT]:
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def update(self, entity: ModelT) -> ModelT:
        await self.session.merge(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def soft_delete(self, entity: Any) -> None:
        if hasattr(entity, "is_deleted"):
            entity.is_deleted = True
            await self.session.flush()

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        for attr, value in filters.items():
            if hasattr(self.model, attr) and value is not None:
                stmt = stmt.where(getattr(self.model, attr) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, **filters: Any) -> bool:
        stmt = select(self.model).limit(1)
        for attr, value in filters.items():
            if hasattr(self.model, attr):
                stmt = stmt.where(getattr(self.model, attr) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
