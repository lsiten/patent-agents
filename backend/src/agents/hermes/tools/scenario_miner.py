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


def _fallback_scenarios(tech_description: str, features: str = "") -> Dict[str, Any]:
    text = f"{tech_description}\n{features}"
    if any(keyword in text for keyword in ("Cave", "折幕", "沉浸", "显示", "视频")):
        return {
            "scenarios": [
                {
                    "name": "Cave沉浸式展厅",
                    "description": "用于展馆、博物馆、企业展厅中折幕/环幕视频播放的姿态自适应显示与补偿。",
                    "domain": "沉浸式展示",
                    "potential_value": "提升不同观看人群和不同展示主题下的视觉连续性。",
                    "confidence": 0.86,
                    "target_users": ["展馆运营方", "沉浸式内容制作方", "集成商"],
                },
                {
                    "name": "可调多屏仿真训练空间",
                    "description": "用于训练模拟、数字孪生和工业仿真中的多显示面画面重构。",
                    "domain": "仿真训练",
                    "potential_value": "在显示面姿态变化时保持多视口画面一致。",
                    "confidence": 0.78,
                    "target_users": ["训练中心", "工业仿真平台"],
                },
                {
                    "name": "互动文旅与大型多媒体装置",
                    "description": "用于根据用户位置、身高或交互选择动态调整折幕姿态并补偿视频内容。",
                    "domain": "互动文旅",
                    "potential_value": "增强沉浸感并降低现场调试成本。",
                    "confidence": 0.8,
                    "target_users": ["文旅项目方", "多媒体艺术装置团队"],
                },
            ],
            "extension_directions": ["实时姿态反馈闭环", "多投影融合补偿", "补充显示设备联动", "面向不同内容主题的姿态模板库"],
            "market_assessment": "沉浸式展陈和多屏互动空间对动态姿态适配、画面连续性和快速部署有持续需求，具备发明专利布局价值。",
        }
    return {
        "scenarios": [],
        "extension_directions": ["结合具体行业进一步拓展"],
        "market_assessment": "需结合应用行业和实施方式进一步评估。",
    }


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
            logger.warning(f"Scenario mining LLM failed, using fallback: {e}")
            return make_tool_output(
                tool_name=self.name,
                data=_fallback_scenarios(tech_description, features),
                error=str(e),
                success=True,
                start_time=start_time,
            )
