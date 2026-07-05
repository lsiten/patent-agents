"""Claim Quality Analyzer Tool - 权利要求客观规则检查工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.core.patent.compliance import validate_claim_rules, split_claims_text

logger = get_logger(__name__)


class ClaimQualityAnalyzerTool(HermesTool):
    """权利要求客观规则检查工具"""
    name = "claim_quality_analyzer"
    description = "检查权利要求中可确定的格式、编号、口语化和必要术语信号；质量结论由 Agent 判断"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "claims": HermesToolParameter(
                    type="string",
                    description="权利要求书完整内容",
                    required=True,
                ),
            },
        )

    async def execute(self, claims: str, **kwargs) -> Dict[str, Any]:
        """执行权利要求客观检查：只返回确定信号，不给质量结论。"""
        start_time = datetime.now()
        logger.info("Analyzing claim quality")

        try:
            text = claims or ""
            claim_numbers = re.findall(r"(?:^|\n)\s*(\d+)[\.、]", text)
            issues = []
            if not claim_numbers:
                issues.append({"claim_number": 1, "issue_type": "format", "description": "未识别到规范编号的权利要求", "suggestion": "按1、2、3或1. 2.格式重排。"})
            if len(text) < 300:
                issues.append({"claim_number": 1, "issue_type": "support", "description": "权利要求内容过短，可能未覆盖完整技术方案", "suggestion": "基于当前发明事实补充输入获取、核心处理、结果输出及必要从属限定。"})
            if re.search(r"比如|这个|东西|然后|你", text):
                issues.append({"claim_number": 1, "issue_type": "clarity", "description": "存在口语化表述", "suggestion": "改为专利规范术语。"})
            if "其特征在于" not in text and "包括" not in text:
                issues.append({"claim_number": 1, "issue_type": "clarity", "description": "独立权利要求缺少清楚的开放式限定", "suggestion": "使用“包括”组织技术特征。"})

            claim_blocks = split_claims_text(text)
            for idx, block in enumerate(claim_blocks[1:], start=2):
                if len(block) < 80:
                    issues.append({
                        "claim_number": idx,
                        "issue_type": "substantive",
                        "severity": "high",
                        "description": f"权利要求{idx}过于简略，缺少具体附加技术特征",
                        "suggestion": "补充参数范围、替代方案、子步骤、组合方式、结构关系或技术效果等实质性限定内容。",
                        "target_agent": "patent_writer",
                    })
                else:
                    has_substantive_limitation = any(term in block for term in [
                        "范围", "阈值", "频率", "强度", "精度", "时间", "长度", "速率",
                        "至少", "至多", "大于", "小于", "等于", "之间", "包括",
                        "步骤", "模块", "单元", "装置", "设备", "系统",
                        "替代", "可选", "或者", "以及", "并且",
                        "通过", "利用", "基于", "根据", "结合", "协同",
                    ])
                    if not has_substantive_limitation:
                        issues.append({
                            "claim_number": idx,
                            "issue_type": "substantive",
                            "severity": "medium",
                            "description": f"权利要求{idx}可能缺少实质性限定内容",
                            "suggestion": "检查是否包含参数范围、子步骤、替代方案或技术效果等附加技术特征。",
                            "target_agent": "patent_writer",
                        })
            hard_rule_report = validate_claim_rules(text)
            for issue in hard_rule_report.get("issues", []):
                issues.append({
                    "claim_number": int(re.search(r"\d+", issue.get("location", "1")).group(0)) if re.search(r"\d+", issue.get("location", "1")) else 1,
                    "issue_type": "format",
                    "severity": issue.get("severity", "medium"),
                    "description": issue.get("issue", ""),
                    "suggestion": issue.get("suggestion", ""),
                    "target_agent": issue.get("target_agent", "patent_writer"),
                })
            dependent_blocks = claim_blocks[1:] if len(claim_blocks) > 1 else []
            avg_dependent_length = sum(len(b) for b in dependent_blocks) / len(dependent_blocks) if dependent_blocks else 0
            short_dependent_count = sum(1 for b in dependent_blocks if len(b) < 80)
            data = {
                "objective_findings": issues,
                "metrics": {
                    "claim_count": len(claim_numbers),
                    "text_length": len(text),
                    "has_open_transition": "包括" in text or "其特征在于" in text,
                    "has_oral_terms": bool(re.search(r"比如|这个|东西|然后|你", text)),
                    "dependent_claim_count": len(dependent_blocks),
                    "avg_dependent_length": round(avg_dependent_length, 1),
                    "short_dependent_count": short_dependent_count,
                    **hard_rule_report.get("metrics", {}),
                },
                "hard_rule_report": hard_rule_report,
                "requires_agent_judgment": [
                    "清楚性是否可接受",
                    "保护范围宽窄是否合适",
                    "创造性支撑是否充分",
                    "从属权利要求充实度是否足够",
                    "是否需要 CEO 调度撰写 Agent 修改",
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
            logger.error(f"Claim quality analysis failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
