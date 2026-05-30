"""
Support Verifier Tool - 支持验证工具
验证说明书是否充分支持权利要求
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

VERIFY_PROMPT = """你是一位专利审查专家。请逐条验证以下权利要求是否得到说明书的充分支持（专利法第26条第4款）。

权利要求：
{claims}

说明书：
{description}

验证标准：
- 权利要求中的每个技术特征是否在说明书中有对应记载
- 概括式保护是否有充分的实施例支持
- 功能性限定是否有具体实施方式支持

请输出 JSON 格式：
{{
  "verification_results": [
    {{
      "claim_number": 1,
      "verdict": "supported/partially_supported/unsupported",
      "evidence": "支持依据所在位置",
      "missing_support": ["缺失的支持内容"],
      "fix_suggestion": "修复建议"
    }}
  ],
  "overall_verdict": "通过/需修改/不通过",
  "critical_gaps": ["关键缺陷"]
}}"""


class SupportVerifierTool(HermesTool):
    """支持验证工具"""
    name = "support_verifier"
    description = "验证说明书对权利要求的支持充分性（专利法第26条第4款）"

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
        """执行支持验证"""
        logger.info("Verifying claim support from description")
        llm = get_llm_service()
        prompt = VERIFY_PROMPT.format(claims=claims, description=description)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"verification_result": response.content, "tool": self.name}
