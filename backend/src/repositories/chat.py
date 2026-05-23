from sqlalchemy import select
from src.repositories.base import BaseRepository
from src.models.chat import ChatSession, ChatMessage


class ChatSessionRepository(BaseRepository[ChatSession]):
    def __init__(self, session):
        super().__init__(session, ChatSession)

    async def get_by_user_id(self, user_id: str) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ChatMessageRepository(BaseRepository[ChatMessage]):
    def __init__(self, session):
        super().__init__(session, ChatMessage)

    async def get_by_session_id(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
