"""
Patent Search Tool - 专利检索工具
对接多源专利数据库进行现有技术检索
"""
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

SEARCH_PROMPT = """你是一位专利检索专家。请根据以下检索请求，模拟执行多源专利检索并返回结果。

检索查询：{query}
数据源：{sources}
结果数量限制：{limit}

请输出 JSON 格式的检索结果：
{{
  "results": [
    {{
      "patent_id": "专利号",
      "title": "专利标题",
      "abstract": "摘要",
      "applicant": "申请人",
      "publication_date": "公开日",
      "source": "数据来源",
      "relevance_score": 0.85
    }}
  ],
  "total_found": 数量,
  "search_strategy": "检索策略说明",
  "keywords_used": ["关键词1", "关键词2"]
}}"""


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
        logger.info("Searching patents", query=query[:50], sources=sources)
        llm = get_llm_service()
        prompt = SEARCH_PROMPT.format(query=query, sources=sources, limit=limit)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"search_results": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("patent_search", PatentSearchTool)
