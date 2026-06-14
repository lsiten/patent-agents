"""
QualityAssessorTool - 确定性质量信号工具

该工具只提取可代码化验证的客观信号，不在工具层判断内容质量是否达标。
质量结论、是否迭代以及如何修改必须由调用该工具的 Hermes Agent LLM 决定。
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


TRANSCRIPT_PATTERN = re.compile(r"[\u4e00-\u9fa5A-Za-z]{1,12}\(\d{2}:\d{2}:\d{2}\)|\d{2}:\d{2}:\d{2}")
DUPLICATE_FIGURE_PATTERN = re.compile(r"图\s*(\d+)\s*图\s*\1")


class QualityAssessorTool(HermesTool):
    """提取阶段输出的确定性质量信号。"""

    name = "quality_assessor"
    description = "提取阶段输出中的结构、完整性、格式和明显缺失信号；质量判断由Agent完成"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "phase_name": HermesToolParameter(
                    type="string",
                    description="阶段名称：requirement / retrieval / writing / review",
                    required=True,
                ),
                "output_content": HermesToolParameter(
                    type="string",
                    description="该阶段的产出内容（JSON或文本）",
                    required=True,
                ),
                "requirements": HermesToolParameter(
                    type="string",
                    description="质量要求或验收标准；工具仅做关键词/格式匹配，不做语义判断",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        phase_name: str = "",
        output_content: str = "",
        document: str = "",
        assessment_type: str = "",
        requirements: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """提取确定性质量信号。"""
        if not phase_name:
            phase_name = assessment_type or kwargs.get("phase_name", "requirement")
        if not output_content:
            output_content = document or kwargs.get("output_content", "")

        logger.info("Collecting objective quality signals", phase=phase_name)

        parsed_json = self._parse_json(output_content)
        content_lower = output_content.lower()
        objective_findings: List[Dict[str, Any]] = []

        required_markers = self._required_markers_for_phase(phase_name)
        marker_presence = {
            marker: (marker.lower() in content_lower or marker in output_content)
            for marker in required_markers
        }
        missing_markers = [marker for marker, present in marker_presence.items() if not present]
        for marker in missing_markers:
            objective_findings.append({
                "type": "missing_expected_marker",
                "marker": marker,
                "source": "deterministic_marker_check",
            })

        if phase_name in {"writing", "review"}:
            if TRANSCRIPT_PATTERN.search(output_content):
                objective_findings.append({
                    "type": "transcript_format_residue",
                    "pattern": "speaker_or_timestamp",
                    "source": "regex",
                })
            if DUPLICATE_FIGURE_PATTERN.search(output_content):
                objective_findings.append({
                    "type": "duplicate_figure_caption",
                    "pattern": "图N 图N",
                    "source": "regex",
                })

        if requirements:
            requirement_terms = self._extract_requirement_terms(requirements)
            missing_requirement_terms = [
                term for term in requirement_terms if term not in output_content
            ]
        else:
            requirement_terms = []
            missing_requirement_terms = []

        return {
            "phase": phase_name,
            "objective_signals": {
                "content_length": len(output_content),
                "is_json": parsed_json is not None,
                "top_level_keys": sorted(parsed_json.keys()) if isinstance(parsed_json, dict) else [],
                "expected_marker_presence": marker_presence,
                "missing_expected_markers": missing_markers,
                "requirement_terms_checked": requirement_terms,
                "missing_requirement_terms": missing_requirement_terms,
                "transcript_residue_count": len(TRANSCRIPT_PATTERN.findall(output_content)),
                "duplicate_figure_caption_count": len(DUPLICATE_FIGURE_PATTERN.findall(output_content)),
            },
            "objective_findings": objective_findings,
            "requires_agent_judgment": [
                "阶段输出质量是否可接受",
                "是否需要进入下一轮迭代",
                "应由哪个Agent补充或修改",
                "如何依据审查问题优化内容",
            ],
            "assessment_timestamp": datetime.now().isoformat(),
        }

    def _parse_json(self, content: str) -> Any:
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None

    def _required_markers_for_phase(self, phase_name: str) -> List[str]:
        return {
            "requirement": ["技术领域", "技术问题", "创新点", "应用场景"],
            "retrieval": ["检索", "现有技术", "对比", "差异"],
            "writing": ["权利要求", "说明书", "摘要", "附图"],
            "review": ["问题", "建议", "审查", "结论"],
        }.get(phase_name, [])

    def _extract_requirement_terms(self, requirements: str) -> List[str]:
        terms = re.split(r"[\s,，;；。.\n]+", requirements)
        return [term for term in terms if len(term) >= 2][:30]
