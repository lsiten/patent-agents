"""Patent Strategy Guide Tool - 专利策略候选项工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

KEYWORD_OPTIONS = [
    (("Cave", "折幕", "多屏", "显示", "投影"), "方法+系统双独权候选：显示面姿态变化后的连续化视频处理闭环"),
    (("姿态", "角度", "身高", "可调"), "候选保护点：目标空间姿态信息获取、姿态参数生成和显示面调节控制"),
    (("裁剪", "补偿", "重映射", "重排", "空白"), "候选保护点：外转空白补偿、内转遮挡裁剪、边界重叠/空白区域判定"),
    (("同步", "输出", "视频"), "候选从属保护点：多显示面同步输出、帧级映射和时序一致性"),
]


def _matches(text: str, words: List[str]) -> bool:
    return any(word.lower() in text.lower() for word in words)


class PatentStrategyGuideTool(HermesTool):
    """专利策略候选项工具"""
    name = "patent_strategy_guide"
    description = "基于关键词给出策略候选项与检查清单；最终申请策略由 Agent 判断"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术方案描述",
                    required=True,
                ),
                "market_info": HermesToolParameter(
                    type="string",
                    description="市场和竞争信息（可选）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, tech_description: str, market_info: str = "未提供", **kwargs
    ) -> Dict[str, Any]:
        """Return deterministic strategy options for the Agent to reason over."""
        start_time = datetime.now()
        logger.info("Generating patent strategy guidance without nested LLM")
        text = f"{tech_description}\n{market_info}"
        matched_options = [
            option for keywords, option in KEYWORD_OPTIONS if _matches(text, list(keywords))
        ] or ["候选布局项：围绕核心技术特征建立方法、系统、装置和介质的层级保护"]
        has_product = bool(re.search(r"系统|设备|装置|终端|服务器|控制端", text))
        has_method = bool(re.search(r"方法|步骤|流程|处理|生成|确定|控制", text))
        data = {
            "filing_options": {
                "candidate_types": ["invention", "utility_model_if_hardware_structure_is_independent"],
                "candidate_geographic_scope": ["CN"],
                "checks_for_agent": [
                    "是否存在已公开演示或论文/产品发布",
                    "硬件结构是否足以独立成案",
                    "方法、系统、装置和介质是否均有说明书支持",
                ],
            },
            "protection_options": {
                "candidate_focuses": matched_options,
                "candidate_defensive_claims": [
                    "显示面姿态参数获取与更新",
                    "边界投影关系、重叠区域和空白区域判定",
                    "视频内容裁剪、补偿、重映射和同步输出",
                ],
                "candidate_claim_sets": ["method"] + (["system", "device", "storage_medium"] if has_product else []) + ([] if has_method else ["method"]),
            },
            "portfolio_options": {
                "candidate_related_filings": [
                    "显示面姿态标定与校准",
                    "多屏视频连续化映射",
                    "用户身高/观看位置自适应显示",
                ],
            },
            "strategy_checklist": [
                "检查是否避免仅保护屏幕角度调节本身",
                "检查是否避免限定具体 Cave/投影硬件而过窄",
                "检查候选保护点是否均可由逐字稿事实或实施例支持",
            ],
            "requires_agent_judgment": [
                "最终专利类型",
                "核心保护点选择",
                "权利要求宽窄",
                "是否需要分案或系列申请",
            ],
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
