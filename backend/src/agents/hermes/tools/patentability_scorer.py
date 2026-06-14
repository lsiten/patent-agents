"""Patentability Scorer Tool - 专利性客观信号工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

DISTINGUISHING_RULES = {
    "姿态变化触发的视频连续化处理": ["姿态", "变化", "视频", "连续"],
    "外转空白补偿": ["外转", "空白", "补偿"],
    "内转遮挡裁剪/重排": ["内转", "遮挡", "裁剪", "重排"],
    "显示面边界投影关系计算": ["边界", "投影", "关系"],
    "多显示面同步输出": ["多屏", "显示面", "同步", "输出"],
}


def _contains_all(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return all(keyword.lower() in lowered for keyword in keywords)


class PatentabilityScorerTool(HermesTool):
    """专利性客观信号工具"""
    name = "patentability_scorer"
    description = "提取技术方案与现有技术的术语重合和区别特征信号；专利性结论由 Agent 判断"

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
        """执行专利性客观信号提取：不输出新颖性/创造性结论。"""
        start_time = datetime.now()
        logger.info("Scoring patentability")

        try:
            invention_text = invention or ""
            prior_text = prior_art or ""
            invention_terms = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", invention_text))
            prior_terms = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", prior_text))
            overlap_ratio = len(invention_terms & prior_terms) / max(len(invention_terms), 1)
            distinguishing = [
                name for name, keywords in DISTINGUISHING_RULES.items()
                if _contains_all(invention_text, keywords) and not _contains_all(prior_text, keywords)
            ]
            data = {
                "objective_signals": {
                    "term_overlap_ratio": round(overlap_ratio, 3),
                    "overlap_terms": sorted(invention_terms & prior_terms)[:40],
                    "distinguishing_features": distinguishing,
                    "has_method_or_system_language": bool(re.search(r"系统|方法|装置|设备|控制|处理|输出", invention_text)),
                },
                "requires_agent_judgment": [
                    "新颖性是否成立",
                    "区别特征是否产生非显而易见的技术效果",
                    "实用性公开是否充分",
                    "是否需要补充检索或修改权利要求",
                ],
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
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
