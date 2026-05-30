"""
Tech Feature Extractor Tool - 技术特征提取工具
从技术描述中提取关键技术特征和创新点
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

EXTRACT_PROMPT = """你是一位专利技术分析专家。请从以下技术描述中提取关键技术特征。

技术描述：
{tech_description}

请输出 JSON 格式：
{{
  "features": [
    {{
      "name": "特征名称",
      "description": "特征详细描述",
      "is_innovative": true/false,
      "technical_significance": "技术意义说明"
    }}
  ],
  "core_innovation": "核心创新点总结",
  "technical_problem": "解决的技术问题"
}}"""


class TechFeatureExtractorTool(HermesTool):
    """技术特征提取工具"""
    name = "tech_feature_extractor"
    description = "从技术描述中提取关键技术特征、创新点和解决的技术问题"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术发明描述文本",
                    required=True,
                ),
            },
        )

    async def execute(self, tech_description: str, **kwargs) -> Dict[str, Any]:
        """执行技术特征提取"""
        logger.info("Extracting technical features from description")
        llm = get_llm_service()
        prompt = EXTRACT_PROMPT.format(tech_description=tech_description)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.3,
        )
        return {"features_analysis": response.content, "tool": self.name}
