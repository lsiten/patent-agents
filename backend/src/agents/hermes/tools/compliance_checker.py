"""
Compliance Checker Tool - 形式合规检查工具
检查专利文件的格式和形式合规性
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.core.patent_compliance import (
    build_patent_text_from_draft,
    validate_patent_document_structure,
)

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
                "drawings": HermesToolParameter(
                    type="array",
                    description="可选附图元数据数组，每项包含 figure_number/title/file_path 等字段",
                    required=False,
                ),
            },
        )

    async def execute(self, patent_document: str, **kwargs) -> Dict[str, Any]:
        """执行形式合规检查：规则化检查，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Checking formal compliance")

        try:
            text, drawings = self._normalize_input(patent_document, kwargs)
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
                drawings=drawings,
            )
            for issue in manual_report.get("issues", []):
                issues.append({
                    "severity": issue.get("severity", "medium"),
                    "location": issue.get("location", "全文"),
                    "issue": issue.get("issue") or issue.get("description", ""),
                    "suggestion": issue.get("suggestion", ""),
                    "target_agent": issue.get("target_agent", "patent_writer"),
                })
            hard_rule_score = max(
                0,
                100
                - sum(
                    25
                    if i["severity"] == "critical"
                    else 15
                    if i["severity"] == "high"
                    else 8
                    for i in issues
                ),
            )
            hard_rule_status = (
                "no_blocking_signal"
                if hard_rule_score >= 85
                else ("needs_agent_review" if hard_rule_score >= 70 else "blocking_signal")
            )
            data = {
                "compliance_issues": issues,
                "format_issues": [i for i in issues if i.get("severity") in ["critical", "high"]],
                "terminology_issues": [],
                "manual_rule_report": manual_report,
                "hard_rule_status": hard_rule_status,
                "hard_rule_score": hard_rule_score,
                "requires_agent_judgment": [
                    "硬规则信号是否影响进入下一阶段",
                    "是否需要 CEO 调度撰写 Agent 修复",
                    "修复后是否需要再次质量审查",
                ],
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

    def _normalize_input(self, patent_document: Any, kwargs: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """Accept either plain patent text or structured draft JSON.

        Quality Agent often passes the whole draft as JSON. Checking the raw
        JSON string would falsely report missing Chinese sections, so convert
        structured drafts into the same patent text used by hard-rule validators.
        """
        drawings = self._extract_drawings(kwargs)
        if isinstance(patent_document, dict):
            draft = self._extract_draft(patent_document)
            if not drawings:
                drawings = self._extract_drawings(patent_document, draft)
            return build_patent_text_from_draft(draft), drawings

        text = patent_document or ""
        if isinstance(text, str):
            stripped = text.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                    if isinstance(payload, dict):
                        draft = self._extract_draft(payload)
                        if not drawings:
                            drawings = self._extract_drawings(payload, draft)
                        return build_patent_text_from_draft(draft), drawings
                except json.JSONDecodeError:
                    pass
            return stripped, drawings

        return str(text), drawings

    def _extract_draft(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Find the patent draft inside direct or nested review payloads."""
        if not isinstance(payload, dict):
            return {}
        if self._looks_like_draft(payload):
            return payload

        for key in (
            "patent_draft",
            "draft",
            "document",
            "patent_document",
            "current_draft",
            "latest_draft",
        ):
            value = payload.get(key)
            if isinstance(value, dict):
                if self._looks_like_draft(value):
                    return value
                nested = self._extract_draft(value)
                if nested:
                    return nested
            if isinstance(value, str):
                parsed = self._try_parse_json_object(value)
                if parsed:
                    nested = self._extract_draft(parsed)
                    if nested:
                        return nested
        return payload

    def _looks_like_draft(self, value: Dict[str, Any]) -> bool:
        return any(key in value for key in ("claims", "description", "abstract", "drawings")) and any(
            key in value for key in ("title", "patent_title", "claims", "description")
        )

    def _extract_drawings(
        self,
        payload: Dict[str, Any],
        draft: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Collect drawing metadata from direct args, nested draft, or validation facts."""
        for container in (payload, draft or {}):
            if not isinstance(container, dict):
                continue
            drawings = container.get("drawings")
            if isinstance(drawings, list):
                normalized = [item for item in drawings if isinstance(item, dict)]
                if normalized:
                    return normalized

        validation = payload.get("drawing_file_validation") if isinstance(payload, dict) else None
        if isinstance(validation, dict) and isinstance(validation.get("items"), list):
            items = [item for item in validation.get("items", []) if isinstance(item, dict)]
            if items:
                return [
                    {
                        "figure_number": str(item.get("figure_number") or ""),
                        "title": str(item.get("title") or ""),
                        "file_path": str(item.get("file_path") or ""),
                    }
                    for item in items
                ]
        return []

    def _try_parse_json_object(self, value: str) -> Dict[str, Any]:
        text = str(value or "").strip()
        if not (text.startswith("{") and text.endswith("}")):
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
