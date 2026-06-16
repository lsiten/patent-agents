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

def _split_features(features: str) -> list[str]:
    items = []
    for part in re.split(r"[\n；;、,，]+", features or ""):
        clean = part.strip(" -0123456789.）)")
        if len(clean) >= 4:
            items.append(clean[:80])
    return items


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
            if not feature_list:
                return make_tool_output(
                    tool_name=self.name,
                    data={
                        "objective_findings": [
                            {
                                "issue_type": "input_missing",
                                "description": "claim_drafter 未收到可识别的当前发明技术特征",
                                "suggestion": "由专利撰写 Agent 基于需求分析和检索报告提炼真实技术特征后重新调用。",
                            }
                        ]
                    },
                    success=False,
                    error="缺少当前发明技术特征，不能使用默认权利要求骨架。",
                    start_time=start_time,
                )
            data = {
                "claim_outline": {
                    "independent_claim_focus": [
                        "以方法独立权利要求按3步或4步覆盖输入获取、核心处理、结果输出等必要技术特征。",
                        "以系统/装置权利要求覆盖与方法步骤对应的功能模块或结构单元。",
                        "是否需要其他权利要求类型由专利撰写 Agent 结合已确认事实和申请策略判断。",
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
