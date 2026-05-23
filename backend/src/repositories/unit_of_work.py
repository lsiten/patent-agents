from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.repositories.patent import PatentTaskRepository, TaskEventRepository
from src.repositories.document import (
    RequirementDocRepository, RetrievalReportRepository,
    PatentDraftRepository, ReviewReportRepository,
    FinalPatentRepository, DocumentRepository,
)
from src.repositories.chat import ChatSessionRepository, ChatMessageRepository
from src.repositories.agent import (
    AgentRepository, AgentToolRepository, AgentSkillRepository, AgentMemoryRepository,
)


class UnitOfWork:
    """UoW — transaction boundary. Commit/fresh session on entry."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None

        self.patent_tasks: PatentTaskRepository | None = None
        self.task_events: TaskEventRepository | None = None
        self.requirement_docs: RequirementDocRepository | None = None
        self.retrieval_reports: RetrievalReportRepository | None = None
        self.patent_drafts: PatentDraftRepository | None = None
        self.review_reports: ReviewReportRepository | None = None
        self.final_patents: FinalPatentRepository | None = None
        self.documents: DocumentRepository | None = None
        self.chat_sessions: ChatSessionRepository | None = None
        self.chat_messages: ChatMessageRepository | None = None
        self.agents: AgentRepository | None = None
        self.agent_tools: AgentToolRepository | None = None
        self.agent_skills: AgentSkillRepository | None = None
        self.agent_memories: AgentMemoryRepository | None = None

    async def __aenter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        self.patent_tasks = PatentTaskRepository(self.session)
        self.task_events = TaskEventRepository(self.session)
        self.requirement_docs = RequirementDocRepository(self.session)
        self.retrieval_reports = RetrievalReportRepository(self.session)
        self.patent_drafts = PatentDraftRepository(self.session)
        self.review_reports = ReviewReportRepository(self.session)
        self.final_patents = FinalPatentRepository(self.session)
        self.documents = DocumentRepository(self.session)
        self.chat_sessions = ChatSessionRepository(self.session)
        self.chat_messages = ChatMessageRepository(self.session)
        self.agents = AgentRepository(self.session)
        self.agent_tools = AgentToolRepository(self.session)
        self.agent_skills = AgentSkillRepository(self.session)
        self.agent_memories = AgentMemoryRepository(self.session)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self.session:
            await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
