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
    description = "在多源专利数据库(USPTO/EPO/CNIPA/Google Patents)中检索相关现有技术"

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
        self, query: str, sources: str = "", limit: str = "10", **kwargs
    ) -> Dict[str, Any]:
        """执行专利检索"""
        start_time = datetime.now()
        logger.info("Searching patents", query=query[:50], sources=sources)
        
        try:
            manager = get_data_source_manager()
            source_list = [
                source.strip()
                for source in (sources or "").split(",")
                if source.strip()
            ]
            if not source_list:
                preferred_order = ["google_patents", "uspto", "epo", "cnipa", "arxiv"]
                source_list = [
                    source_id
                    for source_id in preferred_order
                    if source_id in manager.sources
                ]
            max_results = max(1, min(int(limit or 10), 50))
            references = await manager.search_all(
                SearchQuery(query=query, max_results=max_results, databases=source_list)
            )
            source_status = getattr(manager, "last_search_status", {}) or {}
            source_status_by_lower = {
                str(source_id).strip().lower(): status
                for source_id, status in source_status.items()
                if str(source_id).strip()
            }

            results: List[Dict[str, Any]] = []
            for ref in references[:max_results]:
                item = ref.model_dump() if hasattr(ref, "model_dump") else dict(ref)
                item["patent_id"] = item.get("reference_id", "")
                item["relevance_score"] = item.get("similarity_score", 0)
                results.append(item)

            source_result_counts: Dict[str, int] = {}
            for item in results:
                source = str(item.get("source") or "unknown").strip().lower()
                if source:
                    source_result_counts[source] = source_result_counts.get(source, 0) + 1
            actual_sources_used = sorted(source_result_counts.keys())
            unavailable_or_empty_sources = [
                source for source in source_list if source.lower() not in source_result_counts
            ]
            skipped_sources = []
            for source in unavailable_or_empty_sources:
                status = source_status_by_lower.get(source.lower()) or {}
                if status.get("error"):
                    skipped_sources.append(source)
            empty_sources = [
                source
                for source in unavailable_or_empty_sources
                if source not in skipped_sources
            ]
            unavailable_reasons = {
                source: (source_status_by_lower.get(source.lower(), {}) or {}).get("error")
                or ("未返回可核验证据" if source in unavailable_or_empty_sources else "")
                for source in source_list
                if source in unavailable_or_empty_sources
            }

            data = {
                "query": query,
                "requested_sources": source_list,
                "sources": actual_sources_used,
                "actual_sources_used": actual_sources_used,
                "source_result_counts": source_result_counts,
                "source_status": source_status,
                "unavailable_or_empty_sources": unavailable_or_empty_sources,
                "skipped_sources": skipped_sources,
                "empty_sources": empty_sources,
                "unavailable_reasons": unavailable_reasons,
                "search_results": results,
                "total_found": len(results),
                "search_strategy": "real_data_source_query",
                "source_handling_policy": (
                    "Unavailable or disabled sources were skipped and recorded. "
                    "Do not block the phase when other verifiable evidence exists; "
                    "if no verifiable evidence exists, revise keywords and try other real sources."
                ),
                "keywords_used": [query],
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
