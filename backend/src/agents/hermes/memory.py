"""
Hermes Agent 记忆系统
支持短期记忆（对话历史）、长期记忆（向量存储）、知识库检索
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryItem:
    """记忆项"""
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    content_type: str = "text"  # text / json / embedding
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    importance_score: float = 0.5  # 重要性评分 0-1
    access_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    ttl_minutes: Optional[int] = None  # 过期时间（分钟），None 表示永久

    def is_expired(self) -> bool:
        """判断是否过期"""
        if self.ttl_minutes is None:
            return False
        expiry_time = self.created_at + timedelta(minutes=self.ttl_minutes)
        return datetime.now() > expiry_time

    def record_access(self) -> None:
        """记录访问"""
        self.access_count += 1
        self.last_accessed = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata,
            "importance_score": self.importance_score,
            "access_count": self.access_count,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "ttl_minutes": self.ttl_minutes,
        }


class MemoryStore(ABC):
    """记忆存储抽象基类"""

    @abstractmethod
    def add(self, item: MemoryItem) -> str:
        """添加记忆"""
        pass

    @abstractmethod
    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """获取记忆"""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> List[Tuple[MemoryItem, float]]:
        """搜索记忆，返回（记忆项，相似度）"""
        pass

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        pass

    @abstractmethod
    def list_all(self) -> List[MemoryItem]:
        """列出所有记忆"""
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        pass


class InMemoryStore(MemoryStore):
    """内存存储实现"""

    def __init__(self):
        self._memories: Dict[str, MemoryItem] = {}
        self._logger = get_logger("in_memory_store")

    def add(self, item: MemoryItem) -> str:
        """添加记忆"""
        self._memories[item.memory_id] = item
        self._logger.debug("Added memory", memory_id=item.memory_id)
        return item.memory_id

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """获取记忆"""
        item = self._memories.get(memory_id)
        if item:
            item.record_access()
        return item

    def search(self, query: str, limit: int = 10, **kwargs) -> List[Tuple[MemoryItem, float]]:
        """
        简单的关键词搜索
        生产环境应使用向量搜索
        """
        query_lower = query.lower()
        results = []

        for item in self._memories.values():
            if item.is_expired():
                continue

            # 简单的关键词匹配评分
            content_lower = item.content.lower()
            score = 0.0

            # 完全匹配
            if query_lower in content_lower:
                score = 0.9
            # 部分关键词匹配
            else:
                query_words = set(query_lower.split())
                content_words = set(content_lower.split())
                if query_words and content_words:
                    overlap = len(query_words & content_words)
                    score = overlap / len(query_words)

            # 加权重要性评分
            score = score * 0.7 + item.importance_score * 0.3

            if score > 0.1:  # 最小匹配阈值
                item.record_access()
                results.append((item, score))

        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def list_all(self) -> List[MemoryItem]:
        """列出所有记忆（排除过期的）"""
        return [item for item in self._memories.values() if not item.is_expired()]

    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        expired_ids = [mid for mid, item in self._memories.items() if item.is_expired()]
        for mid in expired_ids:
            del self._memories[mid]
        if expired_ids:
            self._logger.info("Cleaned up expired memories", count=len(expired_ids))
        return len(expired_ids)


class ShortTermMemory:
    """
    短期记忆 - 管理对话历史
    保存最近的对话，用于上下文保持
    """

    def __init__(self, max_history: int = 20, session_id: Optional[str] = None):
        self.max_history = max_history
        self.session_id = session_id or str(uuid4())
        self._store = InMemoryStore()
        self._logger = get_logger("short_term_memory")

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> str:
        """添加对话消息"""
        item = MemoryItem(
            content=content,
            content_type="message",
            metadata={
                "role": role,
                "session_id": self.session_id,
                **(metadata or {}),
            },
            importance_score=importance,
            ttl_minutes=None,  # 对话消息随会话结束，不单独过期
        )
        memory_id = self._store.add(item)

        # 检查是否需要裁剪
        all_memories = self._store.list_all()
        if len(all_memories) > self.max_history:
            # 按创建时间排序，删除最旧的
            sorted_memories = sorted(all_memories, key=lambda m: m.created_at)
            to_delete = sorted_memories[:-self.max_history]
            for m in to_delete:
                self._store.delete(m.memory_id)
            self._logger.debug("Trimmed old messages", count=len(to_delete))

        return memory_id

    def get_recent_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取最近的消息"""
        memories = self._store.list_all()
        # 按时间排序（最新的在后）
        memories.sort(key=lambda m: m.created_at)

        if limit:
            memories = memories[-limit:]

        return [
            {
                "role": m.metadata.get("role", "unknown"),
                "content": m.content,
                "timestamp": m.created_at,
                "memory_id": m.memory_id,
            }
            for m in memories
        ]

    def get_context_window(self, query: Optional[str] = None, limit: int = 10) -> str:
        """获取上下文窗口（格式化后的字符串）"""
        if query:
            # 如果有查询，搜索相关的消息
            results = self._store.search(query, limit=limit)
            memories = [item for item, score in results]
        else:
            memories = [m for m in self._store.list_all()[-limit:]]

        # 按时间排序
        memories.sort(key=lambda m: m.created_at)

        # 格式化
        lines = []
        for m in memories:
            role = m.metadata.get("role", "unknown").upper()
            lines.append(f"{role}: {m.content}")

        return "\n".join(lines)

    def clear(self) -> None:
        """清空短期记忆"""
        for m in self._store.list_all():
            self._store.delete(m.memory_id)
        self._logger.info("Short term memory cleared")

    def count(self) -> int:
        """获取消息数量"""
        return len(self._store.list_all())


class LongTermMemory:
    """
    长期记忆 - 向量存储
    保存重要的知识和经验，支持语义检索
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self._store = InMemoryStore()
        self._logger = get_logger("long_term_memory")
        # 简单的内存向量存储，生产环境应替换为 FAISS / Chroma / Pinecone 等
        self._vector_dim = 1536  # OpenAI ada-002 维度

    def add_memory(
        self,
        content: str,
        memory_type: str = "general",
        importance: float = 0.5,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_days: Optional[int] = None,
    ) -> str:
        """添加长期记忆"""
        item = MemoryItem(
            content=content,
            content_type=memory_type,
            metadata={
                "user_id": self.user_id,
                **(metadata or {}),
            },
            embedding=embedding,
            importance_score=importance,
            ttl_minutes=ttl_days * 1440 if ttl_days else None,
        )
        memory_id = self._store.add(item)
        self._logger.debug("Added long term memory", memory_id=memory_id, type=memory_type)
        return memory_id

    def add_patent_knowledge(
        self,
        patent_id: str,
        title: str,
        abstract: str,
        claims: Optional[str] = None,
        importance: float = 0.8,
    ) -> str:
        """添加专利知识库条目"""
        content = f"# {title}\n\n## 摘要\n{abstract}"
        if claims:
            content += f"\n\n## 权利要求\n{claims}"

        return self.add_memory(
            content=content,
            memory_type="patent_knowledge",
            importance=importance,
            metadata={
                "patent_id": patent_id,
                "title": title,
            },
        )

    def semantic_search(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        语义搜索
        目前实现为关键词搜索，生产环境应替换为向量相似度搜索
        """
        # 先搜索所有匹配项
        results = self._store.search(query, limit=limit * 2)

        # 按类型过滤
        if memory_type:
            results = [
                (item, score) for item, score in results
                if item.content_type == memory_type
            ]

        # 按分数过滤和排序
        results = [(item, score) for item, score in results if score >= min_score]
        results.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "memory_id": item.memory_id,
                "content": item.content,
                "type": item.content_type,
                "similarity_score": score,
                "importance_score": item.importance_score,
                "metadata": item.metadata,
            }
            for item, score in results[:limit]
        ]

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取记忆"""
        item = self._store.get(memory_id)
        if not item:
            return None
        return {
            "memory_id": item.memory_id,
            "content": item.content,
            "type": item.content_type,
            "importance_score": item.importance_score,
            "metadata": item.metadata,
            "access_count": item.access_count,
        }

    def list_by_type(self, memory_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """按类型列出记忆"""
        memories = self._store.list_all()
        memories = [m for m in memories if m.content_type == memory_type]
        memories.sort(key=lambda m: m.created_at, reverse=True)
        return [
            {
                "memory_id": m.memory_id,
                "content_preview": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                "importance_score": m.importance_score,
                "created_at": m.created_at,
            }
            for m in memories[:limit]
        ]

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        return self._store.delete(memory_id)

    def cleanup(self) -> int:
        """清理过期记忆"""
        return self._store.cleanup_expired()

    def count(self) -> int:
        """获取记忆数量"""
        return len(self._store.list_all())


class KnowledgeBase:
    """
    知识库 - 外部知识检索
    封装专利法、审查指南、判例等专业知识
    """

    def __init__(self, kb_id: str, name: str):
        self.kb_id = kb_id
        self.name = name
        self._store = InMemoryStore()
        self._logger = get_logger(f"kb_{kb_id}")

    def add_entry(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        reference: Optional[str] = None,
    ) -> str:
        """添加知识库条目"""
        item = MemoryItem(
            content=content,
            content_type=category,
            metadata={
                "kb_id": self.kb_id,
                "title": title,
                "tags": tags or [],
                "reference": reference,
            },
            importance_score=0.9,  # 知识库条目默认高重要性
            ttl_minutes=None,  # 永不过期
        )
        entry_id = self._store.add(item)
        self._logger.debug("Added KB entry", title=title, category=category)
        return entry_id

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """搜索知识库"""
        results = self._store.search(query, limit=limit)

        if category:
            results = [
                (item, score) for item, score in results
                if item.content_type == category
            ]

        return [
            {
                "entry_id": item.memory_id,
                "title": item.metadata.get("title", "未知"),
                "content": item.content,
                "category": item.content_type,
                "tags": item.metadata.get("tags", []),
                "reference": item.metadata.get("reference"),
                "relevance_score": score,
            }
            for item, score in results
        ]

    def get_citation(self, entry_id: str) -> Optional[Dict[str, str]]:
        """获取引用格式"""
        item = self._store.get(entry_id)
        if not item:
            return None

        return {
            "title": item.metadata.get("title", ""),
            "source": self.name,
            "reference": item.metadata.get("reference", ""),
            "snippet": item.content[:200] + "..." if len(item.content) > 200 else item.content,
        }

    def count(self) -> int:
        """获取条目数量"""
        return len(self._store.list_all())


class AgentMemoryManager:
    """
    Agent 记忆管理器
    统一管理 Agent 的短期记忆、长期记忆和知识库访问
    """

    def __init__(
        self,
        agent_id: str,
        user_id: Optional[str] = None,
        enable_long_term: bool = True,
        enable_kb: bool = True,
    ):
        self.agent_id = agent_id
        self.user_id = user_id
        self.enable_long_term = enable_long_term
        self.enable_kb = enable_kb

        # 初始化各记忆层
        self.short_term = ShortTermMemory(session_id=agent_id)

        if enable_long_term:
            self.long_term = LongTermMemory(user_id=user_id)

        # 知识库注册表
        self._knowledge_bases: Dict[str, KnowledgeBase] = {}

        self._logger = get_logger("memory_manager")
        self._logger.info(
            "Memory manager initialized",
            agent_id=agent_id,
            long_term_enabled=enable_long_term,
            kb_enabled=enable_kb,
        )

    def register_knowledge_base(self, kb: KnowledgeBase) -> None:
        """注册知识库"""
        self._knowledge_bases[kb.kb_id] = kb
        self._logger.info("Registered knowledge base", kb_id=kb.kb_id)

    def add_chat_message(self, role: str, content: str, **kwargs) -> str:
        """添加聊天消息到短期记忆"""
        return self.short_term.add_message(role, content, **kwargs)

    def get_chat_context(self, limit: int = 10) -> str:
        """获取聊天上下文"""
        return self.short_term.get_context_window(limit=limit)

    def add_important_memory(
        self,
        content: str,
        memory_type: str = "insight",
        importance: float = 0.8,
        **kwargs,
    ) -> Optional[str]:
        """添加重要记忆到长期记忆"""
        if not self.enable_long_term:
            self._logger.warning("Long term memory not enabled")
            return None
        return self.long_term.add_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            **kwargs,
        )

    def retrieve_relevant_memories(
        self,
        query: str,
        long_term_limit: int = 3,
        kb_limit: int = 2,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        检索相关记忆（综合检索）
        从短期记忆、长期记忆、知识库中检索相关内容
        """
        results = {
            "short_term": [],
            "long_term": [],
            "knowledge_bases": [],
        }

        # 从短期记忆检索
        recent_messages = self.short_term.get_recent_messages(limit=5)
        results["short_term"] = [
            {"role": m["role"], "content": m["content"]}
            for m in recent_messages
        ]

        # 从长期记忆检索
        if self.enable_long_term:
            results["long_term"] = self.long_term.semantic_search(
                query=query,
                limit=long_term_limit,
            )

        # 从各知识库检索
        if self.enable_kb:
            for kb_id, kb in self._knowledge_bases.items():
                kb_results = kb.search(query, limit=kb_limit)
                for r in kb_results:
                    r["kb_id"] = kb_id
                    r["kb_name"] = kb.name
                    results["knowledge_bases"].append(r)

        return results

    def search_knowledge_base(
        self,
        kb_id: str,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """搜索指定知识库"""
        kb = self._knowledge_bases.get(kb_id)
        if not kb:
            self._logger.warning("Knowledge base not found", kb_id=kb_id)
            return []
        return kb.search(query, limit=limit)

    def clear_short_term(self) -> None:
        """清空短期记忆"""
        self.short_term.clear()

    def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆摘要"""
        summary = {
            "agent_id": self.agent_id,
            "short_term_count": self.short_term.count(),
            "long_term_enabled": self.enable_long_term,
            "long_term_count": self.long_term.count() if self.enable_long_term else 0,
            "knowledge_bases": {
                kb_id: kb.count() for kb_id, kb in self._knowledge_bases.items()
            },
        }
        return summary

    def cleanup(self) -> Dict[str, int]:
        """清理过期记忆"""
        stats = {
            "short_term_expired": 0,
            "long_term_expired": 0,
        }

        if self.enable_long_term:
            stats["long_term_expired"] = self.long_term.cleanup()

        return stats
