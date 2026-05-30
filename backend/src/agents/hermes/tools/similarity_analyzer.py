"""
Similarity Analyzer Tool - 相似度分析工具
分析发明与现有技术之间的相似度和差异
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

SIMILARITY_PROMPT = """你是一位专利对比分析专家。请分析以下发明与现有技术的相似度和差异。

待分析发明：
{invention}

对比现有技术：
{prior_art}

请输出 JSON 格式：
{{
  "overall_similarity": 0.65,
  "feature_comparison": [
    {{
      "feature": "特征名称",
      "in_invention": true,
      "in_prior_art": true,
      "difference": "差异说明"
    }}
  ],
  "key_differences": ["核心区别1", "核心区别2"],
  "risk_level": "high/medium/low",
  "recommendation": "对比分析结论与建议"
}}"""


class SimilarityAnalyzerTool(HermesTool):
    """相似度分析工具"""
    name = "similarity_analyzer"
    description = "分析发明方案与现有技术的相似度，识别关键差异和风险"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "invention": HermesToolParameter(
                    type="string",
                    description="待分析的发明技术方案描述",
                    required=True,
                ),
                "prior_art": HermesToolParameter(
                    type="string",
                    description="对比的现有技术描述（可含多篇）",
                    required=True,
                ),
            },
        )

    async def execute(
        self, invention: str, prior_art: str, **kwargs
    ) -> Dict[str, Any]:
        """执行相似度分析"""
        logger.info("Analyzing similarity between invention and prior art")
        llm = get_llm_service()
        prompt = SIMILARITY_PROMPT.format(invention=invention, prior_art=prior_art)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"similarity_analysis": response.content, "tool": self.name}
