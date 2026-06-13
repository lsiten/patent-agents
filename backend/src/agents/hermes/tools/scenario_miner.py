"""
Scenario Miner Tool - 应用场景挖掘工具
发现技术发明的潜在应用场景和扩展领域
"""
import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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
      "name": "场景名称",
      "description": "应用场景描述",
      "domain": "所属领域",
      "potential_value": "商业价值评估",
      "confidence": 0.8,
      "target_users": ["目标用户群体1", "目标用户群体2"]
    }}
  ],
  "extension_directions": ["扩展方向1", "扩展方向2"],
  "market_assessment": "市场前景简评"
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
        start_time = datetime.now()
        logger.info("Mining application scenarios")
        
        try:
            llm = get_llm_service()
            prompt = SCENARIO_PROMPT.format(
                tech_description=tech_description, features=features or "未提供"
            )
            response = await asyncio.wait_for(
                llm.chat_completion(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.5,
                ),
                timeout=35,
            )
            
            parsed = _extract_json_from_response(response.content)
            
            # 标准化输出数据
            data = {
                "scenarios": parsed.get("scenarios", []),
                "extension_directions": parsed.get("extension_directions", []),
                "market_assessment": parsed.get("market_assessment", ""),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.warning(f"Scenario mining LLM failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                error=f"Scenario mining requires a real LLM result; no rule fallback was used: {e}",
                success=False,
                start_time=start_time,
            )
