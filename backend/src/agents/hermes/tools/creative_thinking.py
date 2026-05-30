"""
Creative Thinking Tool - 创意思维工具
帮助头脑风暴伙伴激发创意、探索专利保护方向
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

CREATIVE_PROMPT = """你是一位创新思维专家和专利策略师。请对以下技术方案进行创意拓展。

技术描述：
{tech_description}

请从以下角度激发创意：
1. 替代实施方案（相同功能的不同技术路线）
2. 拓展应用领域（跨领域创新应用）
3. 改进方向（性能提升、成本降低等）
4. 组合创新（与其他技术的结合点）

请输出 JSON 格式：
{{
  "alternative_embodiments": [
    {{
      "idea": "替代方案描述",
      "technical_approach": "技术路线",
      "patentability": "专利价值评估"
    }}
  ],
  "cross_domain_applications": ["跨领域应用1", "跨领域应用2"],
  "improvement_directions": [
    {{
      "direction": "改进方向",
      "potential_benefit": "预期收益",
      "feasibility": "high/medium/low"
    }}
  ],
  "combination_innovations": ["组合创新点1"],
  "strategic_insights": "整体创新策略建议"
}}"""


class CreativeThinkingTool(HermesTool):
    """创意思维工具"""
    name = "creative_thinking"
    description = "基于技术方案激发创新思维，探索替代方案和拓展方向"

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
            },
        )

    async def execute(self, tech_description: str, **kwargs) -> Dict[str, Any]:
        """执行创意激发"""
        logger.info("Generating creative patent ideas")
        llm = get_llm_service()
        prompt = CREATIVE_PROMPT.format(tech_description=tech_description)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.7,
        )
        return {"creative_ideas": response.content, "tool": self.name}
