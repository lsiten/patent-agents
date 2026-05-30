"""
Patentability Scorer Tool - 专利性评分工具
评估技术方案的新颖性、创造性和实用性
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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


def _parse_llm_json(content: str) -> Dict[str, Any]:
    """从 LLM 输出中解析 JSON，处理 markdown 代码块等情况"""
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    brace_match = re.search(r'\{[\s\S]*\}', content)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return {"raw_content": content}


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
        start_time = datetime.now()
        logger.info("Scoring patentability")
        
        try:
            llm = get_llm_service()
            prompt = SCORE_PROMPT.format(invention=invention, prior_art=prior_art)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
            )
            
            # 解析 LLM 返回的 JSON
            parsed = _parse_llm_json(response.content)
            
            # 标准化输出数据
            data = {
                "novelty": parsed.get("novelty", {}),
                "inventive_step": parsed.get("inventive_step", {}),
                "utility": parsed.get("utility", {}),
                "overall_patentability": parsed.get("overall_patentability", "unknown"),
                "recommendation": parsed.get("recommendation", ""),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content if "raw_content" in parsed else None,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"Patentability scoring failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
