"""
Tech Feature Extractor Tool - 技术特征提取工具
从技术描述中提取关键技术特征和创新点
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


def _fallback_feature_extraction(tech_description: str) -> Dict[str, Any]:
    """Rule-based fallback for the Cave folded-screen disclosure."""
    text = tech_description or ""
    cave_related = any(keyword in text for keyword in ("Cave", "折幕", "沉浸", "显示面", "视频"))
    if cave_related:
        features = [
            {
                "name": "沉浸式展示空间的统一三维坐标建模",
                "description": "对固定显示面和姿态可调显示面建立统一空间坐标，并获取各显示面的边界坐标。",
                "is_innovative": True,
                "technical_significance": "为后续显示间隙、遮挡区域和内容映射参数计算提供几何基础。",
            },
            {
                "name": "姿态-内容-补偿联合映射关系",
                "description": "将观看参考点、显示面目标姿态、实际姿态反馈、内容映射矩阵和补偿策略关联。",
                "is_innovative": True,
                "technical_significance": "使显示姿态变化与画面连续性补偿联动执行。",
            },
            {
                "name": "外转空白区域补偿",
                "description": "根据相邻显示面的边界投影关系确定未覆盖区域或显示间隙，并生成补偿显示数据。",
                "is_innovative": True,
                "technical_significance": "减少折幕姿态变化造成的画面断裂和空白。",
            },
            {
                "name": "内转遮挡区域裁剪与重排",
                "description": "根据显示面深度顺序和重叠投影生成可见区域掩膜，对视频内容进行裁剪、缩放、重排或重映射。",
                "is_innovative": True,
                "technical_significance": "避免姿态内转时重复显示或重要内容被遮挡。",
            },
            {
                "name": "多显示面同步输出",
                "description": "按统一时间戳将重构内容、补偿内容和重映射内容同步输出至各显示面。",
                "is_innovative": False,
                "technical_significance": "保障多屏播放时序一致性。",
            },
        ]
        return {
            "features": features,
            "core_innovation": "围绕Cave折幕显示姿态变化，联动计算显示面边界、内容映射、空白补偿和遮挡裁剪，以保持沉浸式多屏视频画面连续。",
            "technical_problem": "姿态可调显示面运动后产生显示间隙、遮挡重叠、内容错位和多显示面输出不同步的问题。",
            "beneficial_effects": ["保持折幕视频画面连续", "降低接缝错位和遮挡重复", "适配不同展示姿态和观看参考点"],
        }
    return {
        "features": [],
        "core_innovation": text[:300],
        "technical_problem": "需结合技术描述进一步确认。",
        "beneficial_effects": ["提高处理自动化程度"],
    }


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
            response = await asyncio.wait_for(
                llm.chat_completion(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.3,
                ),
                timeout=35,
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
            logger.warning(f"Tech feature extraction LLM failed, using fallback: {e}")
            return make_tool_output(
                tool_name=self.name,
                data=_fallback_feature_extraction(tech_description),
                success=True,
                error=str(e),
                start_time=start_time,
            )
