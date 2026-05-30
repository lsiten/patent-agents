"""
Claim Quality Analyzer Tool - 权利要求质量分析工具
分析权利要求的清楚性、保护范围和撰写质量
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

QUALITY_PROMPT = """你是一位资深专利审查员。请分析以下权利要求的撰写质量。

权利要求：
{claims}

请从以下维度评分(0-100)并分析：
1. 清楚性 - 是否清楚界定保护范围
2. 简要性 - 是否简洁无冗余
3. 支持性 - 是否可获得说明书支持
4. 保护范围 - 宽度是否合适
5. 层次性 - 独立/从属关系是否合理

请输出 JSON 格式：
{{
  "clarity_score": 85,
  "conciseness_score": 80,
  "support_score": 75,
  "breadth_score": 70,
  "hierarchy_score": 90,
  "overall_quality": 80,
  "issues": [
    {{
      "claim_number": 1,
      "issue_type": "clarity/support/breadth",
      "description": "问题描述",
      "suggestion": "改进建议"
    }}
  ],
  "strengths": ["优点1"],
  "recommendation": "总体改进建议"
}}"""


class ClaimQualityAnalyzerTool(HermesTool):
    """权利要求质量分析工具"""
    name = "claim_quality_analyzer"
    description = "分析权利要求的清楚性、保护范围、层次结构等质量指标"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "claims": HermesToolParameter(
                    type="string",
                    description="权利要求书完整内容",
                    required=True,
                ),
            },
        )

    async def execute(self, claims: str, **kwargs) -> Dict[str, Any]:
        """执行权利要求质量分析"""
        logger.info("Analyzing claim quality")
        llm = get_llm_service()
        prompt = QUALITY_PROMPT.format(claims=claims)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"quality_analysis": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("claim_quality_analyzer", ClaimQualityAnalyzerTool)
