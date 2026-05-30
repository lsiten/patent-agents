"""
Tech Feature Extractor Tool - 技术特征提取工具
从技术描述中提取关键技术特征和创新点
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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
  "technical_problem": "解决的技术问题",
  "beneficial_effects": ["有益效果1", "有益效果2"]
}}"""


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


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
        start_time = datetime.now()
        logger.info("Extracting technical features from description")
        
        try:
            llm = get_llm_service()
            prompt = EXTRACT_PROMPT.format(tech_description=tech_description)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
            )
            
            parsed = _extract_json_from_response(response.content)
            
            # 标准化输出数据
            data = {
                "features": parsed.get("features", []),
                "core_innovation": parsed.get("core_innovation", ""),
                "technical_problem": parsed.get("technical_problem", ""),
                "beneficial_effects": parsed.get("beneficial_effects", []),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"Tech feature extraction failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
