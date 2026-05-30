"""
Patentability Scorer Tool - 专利性评分工具
评估技术方案的新颖性、创造性和实用性
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

SCORE_PROMPT = """你是一位专利审查专家。请对以下技术方案进行专利性三性评估。

技术方案：
{invention}

相关现有技术：
{prior_art}

请从新颖性、创造性、实用性三个维度打分(0-100)，并输出 JSON：
{{
  "novelty": {{
    "score": 85,
    "rationale": "新颖性评估理由",
    "related_prior_art": ["相关在先技术"]
  }},
  "inventive_step": {{
    "score": 75,
    "rationale": "创造性评估理由",
    "distinguishing_features": ["区别特征"]
  }},
  "utility": {{
    "score": 90,
    "rationale": "实用性评估理由"
  }},
  "overall_patentability": "high/medium/low",
  "recommendation": "综合建议"
}}"""


class PatentabilityScorerTool(HermesTool):
    """专利性评分工具"""
    name = "patentability_scorer"
    description = "评估技术方案的新颖性、创造性和实用性，给出综合专利性评分"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "invention": HermesToolParameter(
                    type="string",
                    description="待评估的技术方案描述",
                    required=True,
                ),
                "prior_art": HermesToolParameter(
                    type="string",
                    description="相关现有技术（检索结果摘要）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, invention: str, prior_art: str = "未提供", **kwargs
    ) -> Dict[str, Any]:
        """执行专利性评分"""
        logger.info("Scoring patentability")
        llm = get_llm_service()
        prompt = SCORE_PROMPT.format(invention=invention, prior_art=prior_art)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"patentability_score": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("patentability_scorer", PatentabilityScorerTool)
