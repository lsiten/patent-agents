"""
Similarity Analyzer Tool - 相似度分析工具
分析发明与现有技术之间的相似度和差异
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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
        start_time = datetime.now()
        logger.info("Analyzing similarity between invention and prior art")
        
        try:
            llm = get_llm_service()
            prompt = SIMILARITY_PROMPT.format(invention=invention, prior_art=prior_art)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
            )
            
            # 解析 LLM 返回的 JSON
            parsed = _parse_llm_json(response.content)
            
            # 标准化输出数据
            data = {
                "overall_similarity": parsed.get("overall_similarity", 0),
                "feature_comparison": parsed.get("feature_comparison", []),
                "key_differences": parsed.get("key_differences", []),
                "risk_level": parsed.get("risk_level", "unknown"),
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
            logger.error(f"Similarity analysis failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
