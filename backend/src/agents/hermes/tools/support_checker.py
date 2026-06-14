"""
Support Checker Tool - 支持性检查工具
检查权利要求是否得到说明书的充分支持
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

TECH_TERMS = ["姿态", "显示面", "边界", "投影", "重叠", "空白", "补偿", "裁剪", "重映射", "同步输出"]


def _claim_numbers(claims: str) -> list[int]:
    found = [int(item) for item in re.findall(r"(?:^|\n)\s*(\d+)[\.、]", claims or "")]
    return found or [1]


class SupportCheckerTool(HermesTool):
    """支持性检查工具"""
    name = "support_checker"
    description = "检查权利要求与说明书之间的支持关系，识别支持性缺陷"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "claims": HermesToolParameter(
                    type="string",
                    description="权利要求书内容",
                    required=True,
                ),
                "description": HermesToolParameter(
                    type="string",
                    description="说明书内容",
                    required=True,
                ),
            },
        )

    async def execute(self, claims: str, description: str, **kwargs) -> Dict[str, Any]:
        """执行支持性检查：规则化术语覆盖检查，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Checking claim-description support")
        desc = description or ""
        claim_text = claims or ""
        missing_terms = [term for term in TECH_TERMS if term in claim_text and term not in desc]
        results = []
        for number in _claim_numbers(claim_text):
            results.append(
                {
                    "claim_number": number,
                    "support_level": "partial" if missing_terms else "full",
                    "supported_by": "说明书文本中存在对应技术术语" if not missing_terms else "部分术语未在说明书中找到直接对应",
                    "gaps": missing_terms,
                    "suggestion": "请由撰写 Agent 在具体实施方式补充缺失术语的结构、步骤和效果。" if missing_terms else "支持关系初步满足。",
                }
            )
        data = {
            "support_analysis": results,
            "overall_support": "部分支持" if missing_terms else "充分",
            "critical_issues": [f"缺少对“{term}”的说明书支持" for term in missing_terms],
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
