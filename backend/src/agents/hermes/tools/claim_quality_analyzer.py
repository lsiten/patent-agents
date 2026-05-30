"""
Claim Quality Analyzer Tool - 权利要求质量分析工具
分析权利要求的清楚性、保护范围和撰写质量
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


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
        start_time = datetime.now()
        logger.info("Analyzing claim quality")
        
        try:
            llm = get_llm_service()
            prompt = QUALITY_PROMPT.format(claims=claims)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
            )
            
            parsed = _extract_json_from_response(response.content)
            
            # 标准化输出数据
            data = {
                "clarity_score": parsed.get("clarity_score", 0),
                "conciseness_score": parsed.get("conciseness_score", 0),
                "support_score": parsed.get("support_score", 0),
                "breadth_score": parsed.get("breadth_score", 0),
                "hierarchy_score": parsed.get("hierarchy_score", 0),
                "overall_quality": parsed.get("overall_quality", 0),
                "scope_analysis": parsed.get("recommendation", ""),
                "issues": parsed.get("issues", []),
                "strengths": parsed.get("strengths", []),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"Claim quality analysis failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
