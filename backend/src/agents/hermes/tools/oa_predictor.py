"""OA Predictor Tool - 审查意见客观风险信号工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


class OAPredictorTool(HermesTool):
    """审查意见客观风险信号工具"""
    name = "oa_predictor"
    description = "检查可能触发审查风险的客观文本信号；是否构成 OA 风险由 Agent 判断"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "patent_document": HermesToolParameter(
                    type="string",
                    description="专利申请文件内容（权利要求+说明书摘要）",
                    required=True,
                ),
            },
        )

    async def execute(self, patent_document: str, **kwargs) -> Dict[str, Any]:
        """执行审查风险信号检查：不输出主观概率或综合风险。"""
        start_time = datetime.now()
        logger.info("Predicting office action objections")

        try:
            text = patent_document or ""
            signals = []
            if len(text) < 2500:
                signals.append({
                    "type": "sufficiency",
                    "legal_basis": "专利法第26条第3款",
                    "signal": "说明书篇幅偏短",
                    "affected_claims": [1],
                    "candidate_action": "由 Agent 判断是否需要补充具体算法、模块交互、附图说明和实施例。",
                })
            if re.search(r"这个|东西|然后|比如|你", text):
                signals.append({
                    "type": "clarity",
                    "legal_basis": "专利法第26条第4款",
                    "signal": "文本存在口语化表达",
                    "affected_claims": [1],
                    "candidate_action": "由 Agent 判断是否需要替换为专利规范术语并删除逐字稿语言。",
                })
            if "附图说明" in text and not re.search(r"图\d+", text):
                signals.append({
                    "type": "sufficiency",
                    "legal_basis": "专利法实施细则相关形式要求",
                    "signal": "附图说明缺少图号或对应附图",
                    "affected_claims": [],
                    "candidate_action": "由 Agent 判断是否需要生成并插入实际附图，确保图号和说明一一对应。",
                })
            data = {
                "objective_risk_signals": signals,
                "requires_agent_judgment": [
                    "这些信号是否实际构成审查意见风险",
                    "是否需要 CEO 调度撰写 Agent 或附图工具修复",
                    "修复后是否需要再次质量审查",
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
            logger.error(f"OA prediction failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
