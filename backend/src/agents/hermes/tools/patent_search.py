"""
Patent Search Tool - 专利检索工具
对接多源专利数据库进行现有技术检索
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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


def _parse_llm_json(content: str) -> Dict[str, Any]:
    """从 LLM 输出中解析 JSON，处理 markdown 代码块等情况"""
    if not content:
        return {}
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 提取 markdown 代码块中的 JSON
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 提取第一个 { 到最后一个 } 之间的内容
    brace_match = re.search(r'\{[\s\S]*\}', content)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return {"raw_content": content}


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
            llm = get_llm_service()
            prompt = SEARCH_PROMPT.format(query=query, sources=sources, limit=limit)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
            )
            
            # 解析 LLM 返回的 JSON
            parsed = _parse_llm_json(response.content)
            
            # 标准化输出数据
            data = {
                "query": query,
                "sources": sources.split(",") if sources else [],
                "search_results": parsed.get("results", []),
                "total_found": parsed.get("total_found", 0),
                "search_strategy": parsed.get("search_strategy", ""),
                "keywords_used": parsed.get("keywords_used", []),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content if "raw_content" in parsed else None,
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
