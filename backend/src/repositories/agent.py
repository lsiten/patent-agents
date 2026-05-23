from sqlalchemy import select
from src.repositories.base import BaseRepository
from src.models.agent import Agent, AgentTool, AgentSkill, AgentMemory


class AgentRepository(BaseRepository[Agent]):
    def __init__(self, session):
        super().__init__(session, Agent)

    async def get_by_agent_type(self, agent_type: str) -> list[Agent]:
        stmt = select(Agent).where(Agent.agent_type == agent_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_agents(self) -> list[Agent]:
        stmt = select(Agent).where(Agent.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentToolRepository(BaseRepository[AgentTool]):
    def __init__(self, session):
        super().__init__(session, AgentTool)

    async def get_by_agent_id(self, agent_id: str) -> list[AgentTool]:
        stmt = select(AgentTool).where(AgentTool.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentSkillRepository(BaseRepository[AgentSkill]):
    def __init__(self, session):
        super().__init__(session, AgentSkill)

    async def get_by_agent_id(self, agent_id: str) -> list[AgentSkill]:
        stmt = select(AgentSkill).where(AgentSkill.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentMemoryRepository(BaseRepository[AgentMemory]):
    def __init__(self, session):
        super().__init__(session, AgentMemory)

    async def get_by_agent_id(self, agent_id: str) -> list[AgentMemory]:
        stmt = (
            select(AgentMemory)
            .where(AgentMemory.agent_id == agent_id)
            .order_by(AgentMemory.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
