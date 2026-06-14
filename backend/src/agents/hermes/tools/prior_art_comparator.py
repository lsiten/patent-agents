"""对比分析发明与多篇现有技术的技术特征差异。"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


class PriorArtComparatorTool(HermesTool):
    """对比分析发明与多篇现有技术的技术特征差异"""
    name = "prior_art_comparator"
    description = "对比分析发明与多篇现有技术的技术特征差异"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "invention": HermesToolParameter(
                    type="string",
                    description="发明技术方案描述",
                    required=True,
                ),
                "prior_arts": HermesToolParameter(
                    type="string",
                    description="现有技术列表",
                    required=True,
                ),
            },
        )

    async def execute(self, invention: str, prior_arts: str, **kwargs) -> Dict[str, Any]:
        """执行工具逻辑：术语差异对比，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Executing tool", tool=self.name)
        invention_terms = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", invention or ""))
        prior_terms = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", prior_arts or ""))
        data = {
            "common_terms": sorted(invention_terms & prior_terms)[:50],
            "distinguishing_terms": sorted(invention_terms - prior_terms)[:50],
            "prior_art_only_terms": sorted(prior_terms - invention_terms)[:50],
            "comparison_summary": "工具已输出术语级差异；具体创造性论证由检索分析 Agent 结合文献内容完成。",
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
