"""
Compliance Checker Tool - 形式合规检查工具
检查专利文件的格式和形式合规性
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.core.patent_compliance import validate_patent_document_structure

logger = get_logger(__name__)

REQUIRED_SECTIONS = ["技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式", "权利要求书", "摘要"]


class ComplianceCheckerTool(HermesTool):
    """形式合规检查工具"""
    name = "compliance_checker"
    description = "检查专利申请文件的格式和形式合规性，识别格式问题"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "patent_document": HermesToolParameter(
                    type="string",
                    description="专利文件内容（全文或指定部分）",
                    required=True,
                ),
            },
        )

    async def execute(self, patent_document: str, **kwargs) -> Dict[str, Any]:
        """执行形式合规检查：规则化检查，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Checking formal compliance")

        try:
            text = patent_document or ""
            issues = []
            for section in REQUIRED_SECTIONS:
                if section not in text:
                    issues.append({"severity": "high", "location": "全文", "issue": f"缺少{section}章节", "suggestion": f"补充{section}。"})
            if re.search(r"[\u4e00-\u9fa5A-Za-z]+?\(\d{2}:\d{2}:\d{2}\)[:：]", text):
                issues.append({"severity": "critical", "location": "正文", "issue": "存在逐字稿说话人/时间戳格式", "suggestion": "删除对话格式，只保留提炼后的专利技术内容。"})
            duplicate_figs = re.findall(r"图(\d+)\s*图\1", text)
            for fig in sorted(set(duplicate_figs)):
                issues.append({"severity": "high", "location": f"图{fig}", "issue": f"图号重复为“图{fig} 图{fig}”", "suggestion": "图题只保留一次图号。"})
            figure_refs = set(re.findall(r"图(\d+)", text))
            if "附图说明" in text and not figure_refs:
                issues.append({"severity": "medium", "location": "附图说明", "issue": "存在附图说明章节但未发现图号", "suggestion": "补充附图编号和说明。"})
            manual_report = validate_patent_document_structure(
                text,
                drawings=kwargs.get("drawings") if isinstance(kwargs.get("drawings"), list) else None,
            )
            for issue in manual_report.get("issues", []):
                issues.append({
                    "severity": issue.get("severity", "medium"),
                    "location": issue.get("location", "全文"),
                    "issue": issue.get("issue") or issue.get("description", ""),
                    "suggestion": issue.get("suggestion", ""),
                    "target_agent": issue.get("target_agent", "patent_writer"),
                })
            score = max(0, 100 - sum(25 if i["severity"] == "critical" else 15 if i["severity"] == "high" else 8 for i in issues))
            overall = "pass" if score >= 85 else ("conditional_pass" if score >= 70 else "fail")
            data = {
                "compliance_issues": issues,
                "format_issues": [i for i in issues if i.get("severity") in ["critical", "high"]],
                "terminology_issues": [],
                "manual_rule_report": manual_report,
                "overall_compliance": overall,
                "score": score,
                "summary": "规则化形式检查完成；最终结论由质量审查 Agent 综合判定。",
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Compliance check failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
