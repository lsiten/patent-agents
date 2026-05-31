"""
QualityAssessorTool - 质量评估工具
评估各阶段产出的质量，决定是否需要迭代
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


class QualityAssessorTool(HermesTool):
    """
    质量评估工具
    评估各阶段产出的质量，决定是否需要迭代
    """
    name = "quality_assessor"
    description = "评估各阶段产出的质量，判断是否达标，提出改进建议"

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
                    description="质量要求或验收标准",
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
        """执行质量评估"""
        # 兼容 adapter schema 传入的 param alias
        #   adapter schema: document (内容), assessment_type (阶段类型)
        #   tool original:  phase_name, output_content
        if not phase_name:
            phase_name = assessment_type or kwargs.get("phase_name", "requirement")
        if not output_content:
            output_content = document or kwargs.get("output_content", "")
        logger.info("Assessing quality", phase=phase_name)

        # 基础评分维度
        scores = {}
        issues = []
        passed = True

        # 根据阶段类型进行不同的质量检查
        if phase_name == "requirement":
            scores = self._assess_requirement_quality(output_content)
        elif phase_name == "retrieval":
            scores = self._assess_retrieval_quality(output_content)
        elif phase_name == "writing":
            scores = self._assess_writing_quality(output_content)
        elif phase_name == "review":
            scores = self._assess_review_quality(output_content)
        else:
            scores = {"overall": 0.7}

        # 计算总体得分
        overall_score = sum(scores.values()) / len(scores) if scores else 0.7

        # 判断是否通过
        if overall_score < 0.7:
            passed = False
            issues.append({
                "severity": "high",
                "type": "quality_insufficient",
                "description": f"整体质量评分较低（{overall_score:.2f}），建议优化",
            })

        return {
            "phase": phase_name,
            "overall_score": round(overall_score, 2),
            "dimension_scores": scores,
            "passed": passed,
            "needs_iteration": not passed,
            "issues": issues,
            "recommendations": self._generate_recommendations(phase_name, scores, issues),
            "assessment_timestamp": datetime.now().isoformat(),
        }

    def _assess_requirement_quality(self, content: str) -> Dict[str, float]:
        """评估需求分析质量"""
        scores = {}
        content_lower = content.lower()

        # 创新点提取完整性
        scores["innovation_extraction"] = 0.9 if "创新点" in content_lower or "key_innovative_features" in content else 0.6

        # 信息缺口识别
        scores["gap_identification"] = 0.85 if "缺口" in content_lower or "information_gaps" in content else 0.5

        # 应用场景挖掘
        scores["scenario_coverage"] = 0.8 if "应用场景" in content_lower or "application_scenarios" in content else 0.5

        # 结构化程度
        try:
            json.loads(content)
            scores["structured"] = 0.95
        except (json.JSONDecodeError, TypeError):
            scores["structured"] = 0.6

        return scores

    def _assess_retrieval_quality(self, content: str) -> Dict[str, float]:
        """评估检索分析质量"""
        scores = {}
        content_lower = content.lower()

        # 对比文件数量
        scores["prior_art_coverage"] = 0.8 if "similar_patents" in content else 0.5

        # 专利性评估
        scores["patentability_assessment"] = 0.9 if "patentability" in content_lower else 0.5

        # 风险识别
        scores["risk_identification"] = 0.85 if "risk" in content_lower else 0.5

        # 撰写建议
        scores["actionable_guidance"] = 0.8 if "recommendations" in content_lower else 0.4

        return scores

    def _assess_writing_quality(self, content: str) -> Dict[str, float]:
        """评估专利撰写质量"""
        scores = {}
        content_lower = content.lower()

        # 权利要求完整性
        scores["claim_completeness"] = 0.9 if "claims" in content_lower else 0.4

        # 说明书完整性
        scores["description_completeness"] = 0.85 if "description" in content_lower else 0.4

        # 实施例充分性
        scores["embodiment_sufficiency"] = 0.75 if "detailed_description" in content_lower else 0.4

        # 术语一致性
        scores["terminology_consistency"] = 0.8  # 简化处理

        return scores

    def _assess_review_quality(self, content: str) -> Dict[str, float]:
        """评估审查质量"""
        scores = {}
        content_lower = content.lower()

        # 审查维度覆盖
        scores["coverage"] = 0.9 if "claims_review" in content_lower and "description_review" in content_lower else 0.6

        # 问题具体性
        scores["specificity"] = 0.8 if "issues" in content_lower else 0.5

        # 修改建议可操作性
        scores["actionability"] = 0.75 if "suggestion" in content_lower else 0.4

        # OA 预判
        scores["oa_prediction"] = 0.8 if "examination_risks" in content_lower else 0.5

        return scores

    def _generate_recommendations(self, phase: str, scores: Dict[str, float], issues: List) -> List[str]:
        """生成改进建议"""
        recommendations = []

        for dim, score in scores.items():
            if score < 0.7:
                rec_map = {
                    "innovation_extraction": "建议加强核心创新点的提取和描述",
                    "gap_identification": "建议更全面地识别信息缺口，明确需要补充的内容",
                    "prior_art_coverage": "建议扩大检索范围，增加对比文件数量",
                    "patentability_assessment": "建议深化专利性（新颖性、创造性）的评估",
                    "claim_completeness": "建议完善权利要求书，确保覆盖所有核心创新点",
                    "description_completeness": "建议完善说明书内容，确保公开充分",
                    "coverage": "建议增加审查维度的覆盖，确保全面审查",
                }
                if dim in rec_map:
                    recommendations.append(rec_map[dim])

        return recommendations
