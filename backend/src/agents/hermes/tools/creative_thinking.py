"""
Creative Thinking Tool - 创意思维工具
帮助头脑风暴伙伴激发创意、探索专利保护方向
"""
import asyncio
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


def _fallback_creative_ideas(tech_description: str) -> Dict[str, Any]:
    """Rule-based fallback so brainstorming never blocks formal workflow startup."""
    text = (tech_description or "").lower()
    is_cave = any(token in text for token in ["cave", "折幕", "沉浸", "投影", "多屏"])
    if is_cave:
        return {
            "alternative_embodiments": [
                {
                    "idea": "采用多投影面几何标定与边缘融合联合校正的折幕视频处理方案",
                    "technical_approach": "将片源切分、坐标映射、畸变校正和亮度色彩一致性补偿形成连续处理链路",
                    "patentability": "可围绕多折幕空间映射参数生成与实时同步处理形成方法和系统权利要求",
                },
                {
                    "idea": "面向不同幕面夹角的自适应视频重排方案",
                    "technical_approach": "根据幕面姿态、观众视点和播放终端能力动态调整渲染区域与拼接边界",
                    "patentability": "适合保护参数化适配流程、边界融合规则和播放控制装置",
                },
            ],
            "cross_domain_applications": ["沉浸式展厅", "仿真训练", "虚拟制片", "文旅互动空间"],
            "improvement_directions": [
                {
                    "direction": "提高跨幕面画面连续性",
                    "potential_benefit": "降低折线、错位和亮度断层导致的沉浸感破坏",
                    "feasibility": "high",
                },
                {
                    "direction": "降低现场调试复杂度",
                    "potential_benefit": "通过自动标定和模板化参数生成缩短部署时间",
                    "feasibility": "medium",
                },
            ],
            "combination_innovations": [
                "结合深度相机或标定图自动识别幕面几何",
                "结合播放调度系统实现多终端帧同步",
            ],
            "strategic_insights": "建议以“折幕空间参数获取-视频区域分割-几何映射-边缘融合-同步播放”的闭环处理链作为核心保护对象。",
            "source": "rule_fallback",
        }
    return {
        "alternative_embodiments": [
            {
                "idea": "将核心处理流程模块化为数据采集、参数生成、执行控制和结果校验单元",
                "technical_approach": "通过规则引擎或模型推理生成处理参数，并由执行模块完成自动化处理",
                "patentability": "可保护方法步骤、系统模块和存储介质",
            }
        ],
        "cross_domain_applications": ["工业控制", "数字媒体处理", "智能运维"],
        "improvement_directions": [
            {"direction": "自动化程度提升", "potential_benefit": "减少人工配置", "feasibility": "medium"}
        ],
        "combination_innovations": ["与参数优化模型结合", "与质量检测模块结合"],
        "strategic_insights": "建议围绕可验证的处理链路和关键参数生成规则布局权利要求。",
        "source": "rule_fallback",
    }


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
        try:
            llm = get_llm_service()
            prompt = CREATIVE_PROMPT.format(tech_description=tech_description)
            response = await asyncio.wait_for(
                llm.chat_completion(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.7,
                ),
                timeout=35,
            )
            return {"creative_ideas": response.content, "tool": self.name}
        except Exception as e:
            logger.warning(f"Creative thinking LLM failed, using fallback: {e}")
            return {
                "creative_ideas": _fallback_creative_ideas(tech_description),
                "tool": self.name,
                "fallback_used": True,
                "warning": f"creative_thinking_llm_failed: {e}",
            }
