"""Creative Thinking Tool - 创意思维工具."""
import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


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
        """执行创意激发：提供结构化发散方向，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Generating creative patent ideas")
        text = tech_description or ""
        data = {
            "alternative_embodiments": [
                {"idea": "基于显示面姿态参数的边界投影关系计算", "technical_approach": "用目标角度/位置/开合程度建立相邻显示面几何关系", "patentability": "high"},
                {"idea": "基于用户视点或身高的目标空间姿态自适应", "technical_approach": "引入交互终端或传感器获得目标观看位置", "patentability": "medium"},
                {"idea": "投影、LED 或混合显示面的通用化实现", "technical_approach": "上位化为显示面，不限定具体硬件", "patentability": "medium"},
            ],
            "cross_domain_applications": ["数字展厅", "Cave 沉浸空间", "多屏互动影院", "文旅沉浸展示"],
            "improvement_directions": [
                {"direction": "帧级同步输出", "potential_benefit": "减少多屏错位和割裂感", "feasibility": "high"},
                {"direction": "补偿区域内容生成", "potential_benefit": "提升外转空白区域的连续观感", "feasibility": "medium"},
            ],
            "combination_innovations": ["姿态控制+边界判定+视频裁剪/补偿/重映射闭环"],
            "strategic_insights": "Agent 应围绕可调姿态引起的显示内容连续化处理构建保护核心。",
            "source_preview": text[:300],
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
