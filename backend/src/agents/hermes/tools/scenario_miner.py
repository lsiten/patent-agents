"""
Scenario Miner Tool - 应用场景挖掘工具
发现技术发明的潜在应用场景和扩展领域
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

SCENARIO_PROMPT = """你是一位专利应用场景分析专家。请根据以下技术描述和关键特征，挖掘潜在应用场景。

技术描述：
{tech_description}

关键特征：
{features}

请输出 JSON 格式：
{{
  "scenarios": [
    {{
      "scenario": "应用场景描述",
      "domain": "所属领域",
      "potential_value": "商业价值评估",
      "confidence": 0.8,
      "target_users": "目标用户群体"
    }}
  ],
  "extension_directions": ["扩展方向1", "扩展方向2"],
  "market_assessment": "市场前景简评"
}}"""


class ScenarioMinerTool(HermesTool):
    """应用场景挖掘工具"""
    name = "scenario_miner"
    description = "根据技术描述和特征挖掘潜在应用场景、目标用户和市场价值"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术发明描述",
                    required=True,
                ),
                "features": HermesToolParameter(
                    type="string",
                    description="关键技术特征列表（JSON或文本）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, tech_description: str, features: str = "", **kwargs
    ) -> Dict[str, Any]:
        """执行应用场景挖掘"""
        logger.info("Mining application scenarios")
        llm = get_llm_service()
        prompt = SCENARIO_PROMPT.format(
            tech_description=tech_description, features=features or "未提供"
        )
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.5,
        )
        return {"scenarios_analysis": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("scenario_miner", ScenarioMinerTool)
