"""
专利检索与知识库服务
封装外部数据源检索和内部知识库搜索
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger


class PatentService:
    """专利检索与知识库服务"""

    def __init__(
        self,
        data_source_manager=None,
        knowledge_base=None,
    ) -> None:
        self._data_source_manager = data_source_manager
        self._knowledge_base = knowledge_base

    async def search_patents(
        self,
        query: str,
        tech_field: str | None = None,
        max_results: int = 20,
        databases: List[str] | None = None,
    ) -> Dict[str, Any]:
        """搜索现有技术专利"""
        import time

        start = time.time()

        if not self._data_source_manager:
            logger.warning("数据源管理器未配置，返回空结果")
            return {"total": 0, "results": [], "query": query, "search_time": 0.0}

        results = await self._data_source_manager.search_all(
            query=query,
            tech_field=tech_field,
            max_results=max_results,
            databases=databases or [],
        )

        elapsed = time.time() - start
        logger.info(
            "专利搜索完成",
            total=len(results),
            time_seconds=round(elapsed, 2),
            query=query[:60],
        )

        return {
            "total": len(results),
            "results": results,
            "query": query,
            "search_time": elapsed,
        }

    async def search_knowledge_base(
        self, query: str, top_k: int = 5
    ) -> Dict[str, Any]:
        """搜索本地知识库中的定稿专利"""
        if not self._knowledge_base:
            logger.warning("知识库未配置，返回空结果")
            return {"total": 0, "patents": [], "query": query}

        patents = self._knowledge_base.search_similar(query, top_k)

        logger.info(
            "知识库搜索完成",
            total=len(patents),
            query=query[:60],
        )

        return {
            "total": len(patents),
            "patents": patents,
            "query": query,
        }

    async def get_knowledge_base_count(self) -> int:
        """获取知识库专利总数"""
        if not self._knowledge_base:
            return 0
        return len(self._knowledge_base.list_all_patents())

    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        active_tasks = 0  # 由 TaskService 提供

        kb_count = await self.get_knowledge_base_count()

        return {
            "status": "running",
            "active_tasks": active_tasks,
            "agents": [
                {"name": "CEO Agent", "description": "全局流程调度", "status": "idle"},
                {"name": "需求分析Agent", "description": "技术需求结构化", "status": "idle"},
                {"name": "检索分析Agent", "description": "专利性评估", "status": "idle"},
                {"name": "专利撰写Agent", "description": "申请文件生成", "status": "idle"},
                {"name": "质量审查Agent", "description": "合规性检查", "status": "idle"},
            ],
            "knowledge_base_count": kb_count,
            "data_sources": ["uspto", "epo", "cnipa", "google_patents", "arxiv"],
        }
