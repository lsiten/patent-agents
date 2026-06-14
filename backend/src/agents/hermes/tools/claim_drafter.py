"""
Claim Drafter Tool - 权利要求撰写工具
帮助专利撰写 Agent 生成高质量权利要求书
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FEATURES = [
    "获取目标空间姿态信息",
    "确定相邻显示面之间的边界投影关系",
    "识别重叠区域和/或空白区域",
    "对待显示视频内容进行裁剪、补偿和/或重映射",
    "将处理后的视频内容同步输出至对应显示面",
]


def _split_features(features: str) -> list[str]:
    items = []
    for part in re.split(r"[\n；;、,，]+", features or ""):
        clean = part.strip(" -0123456789.）)")
        if len(clean) >= 4:
            items.append(clean[:80])
    return items or DEFAULT_FEATURES


class ClaimDrafterTool(HermesTool):
    """权利要求撰写工具"""
    name = "claim_drafter"
    description = "根据技术特征生成权利要求撰写骨架和特征组织建议"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "features": HermesToolParameter(
                    type="string",
                    description="技术特征列表或描述",
                    required=True,
                ),
                "protection_scope": HermesToolParameter(
                    type="string",
                    description="期望的保护范围说明",
                    required=False,
                ),
            },
        )

    async def execute(
        self, features: str, protection_scope: str = "尽可能宽泛", **kwargs
    ) -> Dict[str, Any]:
        """生成权利要求结构骨架；正式权利要求正文由专利撰写 Agent LLM 完成。"""
        start_time = datetime.now()
        logger.info("Drafting patent claims")

        try:
            feature_list = _split_features(features)
            data = {
                "claim_outline": {
                    "independent_claim_focus": [
                        "以方法独立权利要求覆盖目标空间姿态获取、边界关系判定、画面裁剪/补偿/重映射、同步输出。",
                        "以系统/装置独立权利要求覆盖显示面、姿态反馈、处理控制和显示控制模块。",
                        "以电子设备/存储介质权利要求覆盖软件实现。",
                    ],
                    "dependent_claim_topics": feature_list[:8],
                    "claim_dependency_plan": {
                        "1": [],
                        **{str(i): ["1"] for i in range(2, 2 + min(len(feature_list), 8))},
                    },
                },
                "protection_breadth": protection_scope,
                "drafting_notes": (
                    "工具仅提供结构骨架、特征顺序和保护层级建议；"
                    "正式权利要求文本必须由专利撰写 Agent 的 LLM 自行判断并输出。"
                ),
                "features_used": feature_list,
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Claim drafting failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
