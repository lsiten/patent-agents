"""
Patent Search Tool - 专利检索工具
对接多源专利数据库进行现有技术检索
"""
from datetime import datetime
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.data_sources.base import get_data_source_manager
from src.models.domain import SearchQuery

logger = get_logger(__name__)


class PatentSearchTool(HermesTool):
    """专利检索工具 - 对接多源数据库"""
    name = "patent_search"
    description = "在多源专利数据库(USPTO/EPO/CNIPA)中检索相关现有技术"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "query": HermesToolParameter(
                    type="string",
                    description="检索查询（关键词、技术描述或检索式）",
                    required=True,
                ),
                "sources": HermesToolParameter(
                    type="string",
                    description="数据源，逗号分隔: uspto,epo,cnipa,google_patents",
                    required=False,
                ),
                "limit": HermesToolParameter(
                    type="string",
                    description="最大结果数量",
                    required=False,
                ),
            },
        )

    async def execute(
        self, query: str, sources: str = "uspto,epo", limit: str = "10", **kwargs
    ) -> Dict[str, Any]:
        """执行专利检索"""
        start_time = datetime.now()
        logger.info("Searching patents", query=query[:50], sources=sources)
        
        try:
            source_list = [
                source.strip()
                for source in (sources or "").split(",")
                if source.strip()
            ]
            max_results = max(1, min(int(limit or 10), 50))
            manager = get_data_source_manager()
            references = await manager.search_all(
                SearchQuery(query=query, max_results=max_results, databases=source_list)
            )

            results: List[Dict[str, Any]] = []
            for ref in references[:max_results]:
                item = ref.model_dump() if hasattr(ref, "model_dump") else dict(ref)
                item["patent_id"] = item.get("reference_id", "")
                item["relevance_score"] = item.get("similarity_score", 0)
                results.append(item)

            data = {
                "query": query,
                "sources": source_list,
                "search_results": results,
                "total_found": len(results),
                "search_strategy": "real_data_source_query",
                "keywords_used": [query],
                "mock_used": False,
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"Patent search failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={"query": query, "sources": sources.split(",") if sources else []},
                success=False,
                error=str(e),
                start_time=start_time,
            )
