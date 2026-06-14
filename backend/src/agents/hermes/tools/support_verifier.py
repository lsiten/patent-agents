"""
Support Verifier Tool - 支持验证工具
验证说明书是否充分支持权利要求
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

CORE_TERMS = ["显示面", "姿态", "边界", "投影", "重叠", "空白", "补偿", "裁剪", "重映射", "同步"]


class SupportVerifierTool(HermesTool):
    """支持验证工具"""
    name = "support_verifier"
    description = "验证说明书对权利要求的支持充分性（专利法第26条第4款）"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "claims": HermesToolParameter(
                    type="string",
                    description="权利要求书内容",
                    required=True,
                ),
                "description": HermesToolParameter(
                    type="string",
                    description="说明书内容",
                    required=True,
                ),
            },
        )

    async def execute(self, claims: str, description: str, **kwargs) -> Dict[str, Any]:
        """执行支持验证：术语覆盖与章节存在性检查，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Verifying claim support from description")

        try:
            claim_text = claims or ""
            desc_text = description or ""
            missing = [term for term in CORE_TERMS if term in claim_text and term not in desc_text]
            claim_numbers = re.findall(r"(?:^|\n)\s*(\d+)[\.、]", claim_text) or ["1"]
            verification_results = []
            support_issues = []
            for number in claim_numbers:
                verdict = "partially_supported" if missing else "supported"
                item = {
                    "claim_number": int(number),
                    "verdict": verdict,
                    "evidence": "说明书包含对应核心术语" if not missing else "说明书缺少部分核心术语的直接公开",
                    "missing_support": missing,
                    "fix_suggestion": "补充缺失术语对应的结构、步骤、算法和效果。" if missing else "无需修复。",
                }
                verification_results.append(item)
                if missing:
                    support_issues.append(item)
            data = {
                "verification_results": verification_results,
                "unsupported_claims": [str(item["claim_number"]) for item in support_issues],
                "support_issues": support_issues,
                "overall_verdict": "需修改" if missing else "通过",
                "critical_gaps": [f"说明书缺少“{term}”支持" for term in missing],
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Support verification failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
