from sqlalchemy import select
from src.repositories.base import BaseRepository
from src.models.document import (
    RequirementDoc, RetrievalReport, PatentDraft,
    ReviewReport, FinalPatent, Document,
)


class RequirementDocRepository(BaseRepository[RequirementDoc]):
    def __init__(self, session):
        super().__init__(session, RequirementDoc)

    async def get_by_task_id(self, task_id: str) -> list[RequirementDoc]:
        stmt = select(RequirementDoc).where(RequirementDoc.task_id == task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class RetrievalReportRepository(BaseRepository[RetrievalReport]):
    def __init__(self, session):
        super().__init__(session, RetrievalReport)

    async def get_by_task_id(self, task_id: str) -> list[RetrievalReport]:
        stmt = select(RetrievalReport).where(RetrievalReport.task_id == task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PatentDraftRepository(BaseRepository[PatentDraft]):
    def __init__(self, session):
        super().__init__(session, PatentDraft)

    async def get_by_task_id(self, task_id: str) -> list[PatentDraft]:
        stmt = select(PatentDraft).where(PatentDraft.task_id == task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_task(self, task_id: str) -> PatentDraft | None:
        stmt = (
            select(PatentDraft)
            .where(PatentDraft.task_id == task_id)
            .order_by(PatentDraft.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ReviewReportRepository(BaseRepository[ReviewReport]):
    def __init__(self, session):
        super().__init__(session, ReviewReport)

    async def get_by_task_id(self, task_id: str) -> list[ReviewReport]:
        stmt = select(ReviewReport).where(ReviewReport.task_id == task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class FinalPatentRepository(BaseRepository[FinalPatent]):
    def __init__(self, session):
        super().__init__(session, FinalPatent)

    async def get_by_task_id(self, task_id: str) -> FinalPatent | None:
        stmt = select(FinalPatent).where(FinalPatent.task_id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session):
        super().__init__(session, Document)

    async def get_by_task_id(self, task_id: str) -> list[Document]:
        stmt = select(Document).where(Document.task_id == task_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_doc_type(self, task_id: str, doc_type: str) -> list[Document]:
        stmt = select(Document).where(
            Document.task_id == task_id,
            Document.doc_type == doc_type,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
