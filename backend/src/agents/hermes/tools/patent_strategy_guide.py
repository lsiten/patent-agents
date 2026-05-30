"""
Patent Strategy Guide Tool - 专利策略指导工具
提供专利申请和保护的策略建议
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

STRATEGY_PROMPT = """你是一位资深专利策略顾问。请根据以下技术方案和市场信息，提供专利策略建议。

技术描述：
{tech_description}

市场信息：
{market_info}

请输出 JSON 格式的策略建议：
{{
  "filing_strategy": {{
    "recommended_type": "invention/utility_model/both",
    "geographic_scope": ["CN", "US", "EP"],
    "timeline_suggestion": "申请时间建议",
    "priority_claim": "是否建议优先权主张"
  }},
  "protection_strategy": {{
    "core_claims_focus": "核心保护点建议",
    "defensive_claims": "防御性权利要求建议",
    "claim_breadth": "保护范围宽度建议"
  }},
  "portfolio_strategy": {{
    "related_filings": ["可能的关联申请方向"],
    "continuation_potential": "延续申请潜力",
    "divisional_strategy": "分案策略"
  }},
  "risk_mitigation": [
    {{
      "risk": "风险描述",
      "mitigation": "缓解策略"
    }}
  ],
  "commercial_considerations": "商业化建议"
}}"""


class PatentStrategyGuideTool(HermesTool):
    """专利策略指导工具"""
    name = "patent_strategy_guide"
    description = "基于技术方案和市场情况提供专利申请策略、保护策略和组合策略建议"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术方案描述",
                    required=True,
                ),
                "market_info": HermesToolParameter(
                    type="string",
                    description="市场和竞争信息（可选）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, tech_description: str, market_info: str = "未提供", **kwargs
    ) -> Dict[str, Any]:
        """执行策略指导"""
        logger.info("Generating patent strategy guidance")
        llm = get_llm_service()
        prompt = STRATEGY_PROMPT.format(
            tech_description=tech_description, market_info=market_info
        )
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.4,
        )
        return {"strategy_guidance": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("patent_strategy_guide", PatentStrategyGuideTool)
