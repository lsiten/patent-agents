"""Patent Strategy Guide Tool - 专利策略候选项工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict, List

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

KEYWORD_OPTIONS = [
    (("获取", "采集", "检测", "识别", "输入"), "候选保护点：输入信息获取、预处理和质量控制"),
    (("确定", "生成", "计算", "处理", "控制", "匹配"), "候选保护点：核心处理规则、模型、映射关系或控制策略"),
    (("输出", "执行", "反馈", "更新", "存储", "发送"), "候选从属保护点：结果输出、执行反馈和状态更新"),
    (("异常", "校正", "补偿", "修复", "风险", "误差"), "候选从属保护点：异常处理、校正机制和鲁棒性保障"),
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
                    "候选保护点是否完全来自当前技术事实，而非历史案例模板",
                ],
            },
            "protection_options": {
                "candidate_focuses": matched_options,
                "candidate_defensive_claims": [
                    "输入参数获取与预处理",
                    "核心处理规则或控制策略",
                    "输出结果、反馈更新和异常处理",
                ],
                "candidate_claim_sets": ["method"] + (["system", "device", "storage_medium"] if has_product else []) + ([] if has_method else ["method"]),
            },
            "portfolio_options": {
                "candidate_related_filings": [
                    "核心算法或控制规则优化",
                    "系统模块化实现",
                    "异常处理和反馈校正机制",
                ],
            },
            "strategy_checklist": [
                "检查是否只围绕当前技术事实提炼保护点",
                "检查是否避免限定不必要的具体硬件、场景或业务对象而过窄",
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
