from sqlalchemy import select
from src.repositories.base import BaseRepository
from src.models.patent import PatentTask, TaskEvent


class PatentTaskRepository(BaseRepository[PatentTask]):
    def __init__(self, session):
        super().__init__(session, PatentTask)

    async def get_by_user_id(self, user_id: str, offset: int = 0, limit: int = 100) -> list[PatentTask]:
        stmt = (
            select(PatentTask)
            .where(PatentTask.user_id == user_id)
            .offset(offset).limit(limit)
            .order_by(PatentTask.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_organization(
        self, org_id: str, offset: int = 0, limit: int = 100
    ) -> list[PatentTask]:
        stmt = (
            select(PatentTask)
            .where(PatentTask.organization_id == org_id)
            .offset(offset).limit(limit)
            .order_by(PatentTask.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: str, offset: int = 0, limit: int = 100) -> list[PatentTask]:
        stmt = (
            select(PatentTask)
            .where(PatentTask.status == status)
            .offset(offset).limit(limit)
            .order_by(PatentTask.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class TaskEventRepository(BaseRepository[TaskEvent]):
    def __init__(self, session):
        super().__init__(session, TaskEvent)

    async def get_by_task_id(self, task_id: str) -> list[TaskEvent]:
        stmt = (
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
