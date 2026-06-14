"""
Description Writer Tool - 说明书撰写工具
帮助撰写专利说明书各章节
"""
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

SECTION_NAME_MAP = {
    "technical_field": "技术领域",
    "background": "背景技术",
    "summary": "发明内容",
    "drawings": "附图说明",
    "detailed": "具体实施方式",
}


class DescriptionWriterTool(HermesTool):
    """说明书撰写工具"""
    name = "description_writer"
    description = "撰写专利说明书各章节（技术领域、背景技术、发明内容、具体实施方式等）"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "section_type": HermesToolParameter(
                    type="string",
                    description="章节类型: technical_field/background/summary/drawings/detailed",
                    required=True,
                    enum=["technical_field", "background", "summary", "drawings", "detailed"],
                ),
                "technical_content": HermesToolParameter(
                    type="string",
                    description="该章节涉及的技术内容",
                    required=True,
                ),
                "claims": HermesToolParameter(
                    type="string",
                    description="相关权利要求（用于确保支持性）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, section_type: str, technical_content: str, claims: str = "", **kwargs
    ) -> Dict[str, Any]:
        """生成说明书章节写作计划；正文由专利撰写 Agent 分段完成。"""
        start_time = datetime.now()
        logger.info("Writing patent description section", section=section_type)

        try:
            section_name = SECTION_NAME_MAP.get(section_type, section_type)
            content_hint = (technical_content or "").strip()[:1200]
            section_plan = {
                "technical_field": ["说明本发明属于沉浸式多屏/折幕视频显示处理领域。"],
                "background": ["概述固定显示面与可调显示面在姿态变化时产生遮挡、空白、错位和不同步问题。"],
                "summary": ["围绕姿态获取、边界关系判定、裁剪/补偿/重映射和同步输出描述技术方案及效果。"],
                "drawings": ["逐图列明系统结构、方法流程、边界投影关系、补偿/裁剪示意；不要重复图号。"],
                "detailed": ["按步骤描述目标空间姿态信息、区域判定算法、外转补偿、内转裁剪重排和同步输出实施例。"],
            }.get(section_type, ["围绕技术内容撰写该章节，确保与权利要求一一支持。"])
            data = {
                "section_type": section_type,
                "section_name": section_name,
                "content_outline": section_plan,
                "technical_content_preview": content_hint,
                "claims_reference_present": bool(claims),
                "writing_constraints": [
                    "不得复制逐字稿中的说话人、时间戳或口语格式。",
                    "附图说明必须与实际生成附图一一对应，图号不得重复。",
                    "每个权利要求技术特征应在具体实施方式中有对应公开。",
                ],
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Description writing failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={"section_type": section_type},
                success=False,
                error=str(e),
                start_time=start_time,
            )
