"""
Support Checker Tool - 支持性检查工具
检查权利要求是否得到说明书的充分支持
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

SUPPORT_PROMPT = """你是一位专利审查专家。请检查以下权利要求是否得到说明书的充分支持。

权利要求：
{claims}

说明书内容：
{description}

请输出 JSON 格式：
{{
  "support_analysis": [
    {{
      "claim_number": 1,
      "support_level": "full/partial/insufficient",
      "supported_by": "说明书中支持该权利要求的具体内容",
      "gaps": ["缺失的支持内容"],
      "suggestion": "改进建议"
    }}
  ],
  "overall_support": "充分/部分支持/不充分",
  "critical_issues": ["关键支持性问题"]
}}"""


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
        """执行支持性检查"""
        logger.info("Checking claim-description support")
        llm = get_llm_service()
        prompt = SUPPORT_PROMPT.format(claims=claims, description=description)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"support_check": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("support_checker", SupportCheckerTool)
