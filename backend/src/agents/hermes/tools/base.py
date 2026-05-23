"""
Hermes Agent 工具基类和通用工具
所有专业工具都继承自 HermesTool 基类
"""
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


class TaskPlannerTool(HermesTool):
    """
    任务规划工具
    帮助 CEO Agent 制定专利申请工作计划
    """
    name = "task_planner"
    description = "制定专利申请的工作计划和时间线，分解任务，设定里程碑"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术发明描述",
                    required=True,
                ),
                "patent_type": HermesToolParameter(
                    type="string",
                    description="专利类型：invention(发明) / utility_model(实用新型)",
                    required=False,
                ),
                "priority": HermesToolParameter(
                    type="string",
                    description="优先级：high / medium / low",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        tech_description: str,
        patent_type: str = "invention",
        priority: str = "medium",
    ) -> Dict[str, Any]:
        """执行任务规划"""
        logger.info("Planning patent application task", patent_type=patent_type)

        # 估算各阶段时间（基于专利类型）
        time_estimates = {
            "requirement_analysis": 30,  # 分钟
            "retrieval_analysis": 60,
            "patent_writing": 120,
            "quality_review": 45,
        }

        if patent_type == "utility_model":
            time_estimates = {k: int(v * 0.7) for k, v in time_estimates.items()}

        # 生成任务分解
        tasks = [
            {
                "phase": "requirement_analysis",
                "name": "需求分析",
                "description": "结构化技术描述，提取创新点，识别信息缺口",
                "estimated_time": time_estimates["requirement_analysis"],
                "dependencies": [],
                "output": "需求分析文档",
            },
            {
                "phase": "retrieval_analysis",
                "name": "检索分析",
                "description": "现有技术检索，评估专利性，识别风险",
                "estimated_time": time_estimates["retrieval_analysis"],
                "dependencies": ["requirement_analysis"],
                "output": "检索分析报告",
            },
            {
                "phase": "patent_writing",
                "name": "专利撰写",
                "description": "撰写权利要求书、说明书、摘要等申请文件",
                "estimated_time": time_estimates["patent_writing"],
                "dependencies": ["retrieval_analysis"],
                "output": "专利申请文件",
            },
            {
                "phase": "quality_review",
                "name": "质量审查",
                "description": "形式合规审查，权利要求质量审查，OA预判",
                "estimated_time": time_estimates["quality_review"],
                "dependencies": ["patent_writing"],
                "output": "质量审查报告",
            },
        ]

        # 计算关键指标
        total_time = sum(t["estimated_time"] for t in tasks)
        complexity = "high" if len(tech_description) > 2000 else "medium" if len(tech_description) > 1000 else "low"

        return {
            "plan_id": f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "patent_type": patent_type,
            "priority": priority,
            "complexity_assessment": complexity,
            "total_estimated_time": total_time,
            "phases": tasks,
            "milestones": [
                {"name": "需求确认完成", "after_phase": "requirement_analysis"},
                {"name": "检索完成", "after_phase": "retrieval_analysis"},
                {"name": "初稿完成", "after_phase": "patent_writing"},
                {"name": "最终交付", "after_phase": "quality_review"},
            ],
            "recommendations": [
                "建议在需求分析阶段与发明人充分沟通，确保信息完整",
                "检索阶段建议使用多个数据库交叉验证",
                "撰写阶段重点突出核心创新点的技术效果",
                "审查阶段特别关注权利要求的支持性问题",
            ],
        }


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
        phase_name: str,
        output_content: str,
        requirements: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行质量评估"""
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


class ReportGeneratorTool(HermesTool):
    """
    报告生成工具
    生成各阶段的标准化报告文档
    """
    name = "report_generator"
    description = "生成标准化的报告文档，支持多种格式输出"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "report_type": HermesToolParameter(
                    type="string",
                    description="报告类型：requirement / retrieval / quality / final",
                    required=True,
                ),
                "content": HermesToolParameter(
                    type="string",
                    description="报告内容（JSON格式）",
                    required=True,
                ),
                "format": HermesToolParameter(
                    type="string",
                    description="输出格式：markdown / json / html",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        report_type: str,
        content: str,
        format: str = "markdown",
    ) -> Dict[str, Any]:
        """生成报告"""
        logger.info("Generating report", type=report_type, format=format)

        try:
            data = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            data = {"raw_content": content}

        # 根据报告类型生成不同格式
        if format == "markdown":
            report_content = self._generate_markdown_report(report_type, data)
        elif format == "html":
            report_content = self._generate_html_report(report_type, data)
        else:
            report_content = json.dumps(data, ensure_ascii=False, indent=2)

        return {
            "report_type": report_type,
            "format": format,
            "content": report_content,
            "generated_at": datetime.now().isoformat(),
            "metadata": {
                "sections_count": len(data) if isinstance(data, dict) else 1,
                "word_count": len(report_content),
            },
        }

    def _generate_markdown_report(self, report_type: str, data: Dict) -> str:
        """生成 Markdown 格式报告"""
        title_map = {
            "requirement": "专利申请需求分析报告",
            "retrieval": "专利检索分析报告",
            "quality": "质量审查报告",
            "final": "专利申请最终报告",
        }

        title = title_map.get(report_type, "专利申请报告")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# {title}",
            "",
            f"> 生成时间：{timestamp}",
            "",
            "---",
            "",
        ]

        # 递归生成内容
        def _dict_to_markdown(d: Dict, level: int = 2) -> List[str]:
            result = []
            for key, value in d.items():
                # 将下划线转换为空格并首字母大写
                display_key = key.replace("_", " ").title()
                prefix = "#" * level

                if isinstance(value, dict):
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    result.extend(_dict_to_markdown(value, level + 1))
                    result.append("")
                elif isinstance(value, list):
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    for i, item in enumerate(value, 1):
                        if isinstance(item, dict):
                            result.append(f"**{i}.**")
                            for k, v in item.items():
                                result.append(f"   - **{k}**: {v}")
                        else:
                            result.append(f"- {item}")
                    result.append("")
                else:
                    result.append(f"{prefix} {display_key}")
                    result.append("")
                    result.append(str(value))
                    result.append("")
            return result

        lines.extend(_dict_to_markdown(data))

        # 添加页脚
        lines.extend([
            "---",
            "",
            "> 本报告由专利申请智能体系统自动生成",
        ])

        return "\n".join(lines)

    def _generate_html_report(self, report_type: str, data: Dict) -> str:
        """生成 HTML 格式报告"""
        markdown = self._generate_markdown_report(report_type, data)

        # 简单的 Markdown 到 HTML 转换
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>专利申请报告 - {report_type}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 1000px; margin: 0 auto; padding: 2rem; }}
        h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 0.5rem; }}
        h2 {{ color: #202124; margin-top: 1.5rem; }}
        h3 {{ color: #3c4043; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border: 1px solid #dadce0; padding: 0.75rem; text-align: left; }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        blockquote {{ background-color: #f8f9fa; border-left: 4px solid #1a73e8; padding: 1rem; margin: 1rem 0; }}
        code {{ background-color: #f1f3f4; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; }}
        pre {{ background-color: #f8f9fa; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
    </style>
</head>
<body>
<pre>{markdown}</pre>
</body>
</html>"""
        return html


class RiskAnalyzerTool(HermesTool):
    """
    风险分析工具
    识别专利申请过程中的各种风险
    """
    name = "risk_analyzer"
    description = "分析专利申请过程中的各种风险，提供评估和缓解建议"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "analysis_type": HermesToolParameter(
                    type="string",
                    description="分析类型：novelty / inventive_step / prior_art / support / overall",
                    required=True,
                ),
                "tech_data": HermesToolParameter(
                    type="string",
                    description="技术数据或专利文件内容",
                    required=True,
                ),
                "prior_art_references": HermesToolParameter(
                    type="string",
                    description="现有技术参考文件列表（JSON格式）",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        analysis_type: str,
        tech_data: str,
        prior_art_references: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行风险分析"""
        logger.info("Analyzing risks", type=analysis_type)

        risks = []
        overall_risk_level = "low"

        # 基于分析类型识别风险
        if analysis_type in ["novelty", "overall"]:
            novelty_risks = self._analyze_novelty_risks(tech_data)
            risks.extend(novelty_risks)

        if analysis_type in ["inventive_step", "overall"]:
            inventive_risks = self._analyze_inventive_step_risks(tech_data)
            risks.extend(inventive_risks)

        if analysis_type in ["prior_art", "overall"] and prior_art_references:
            prior_art_risks = self._analyze_prior_art_risks(prior_art_references)
            risks.extend(prior_art_risks)

        if analysis_type in ["support", "overall"]:
            support_risks = self._analyze_support_risks(tech_data)
            risks.extend(support_risks)

        # 计算整体风险等级
        if any(r["severity"] == "critical" for r in risks):
            overall_risk_level = "critical"
        elif any(r["severity"] == "high" for r in risks):
            overall_risk_level = "high"
        elif any(r["severity"] == "medium" for r in risks):
            overall_risk_level = "medium"

        return {
            "analysis_type": analysis_type,
            "overall_risk_level": overall_risk_level,
            "risk_count": len(risks),
            "risks": risks,
            "risk_matrix": self._generate_risk_matrix(risks),
            "mitigation_priorities": self._generate_mitigation_priorities(risks),
            "analysis_timestamp": datetime.now().isoformat(),
        }

    def _analyze_novelty_risks(self, tech_data: str) -> List[Dict]:
        """分析新颖性风险"""
        risks = []
        data_lower = tech_data.lower()

        # 检查是否有过于宽泛的技术描述
        if len(data_lower) < 200:
            risks.append({
                "type": "novelty_insufficient_description",
                "severity": "medium",
                "description": "技术描述不够详细，可能影响新颖性判断的准确性",
                "category": "information",
                "mitigation": "补充更多的技术细节和具体实现方案",
            })

        # 检查是否提到了常见的通用技术
        common_terms = ["人工智能", "机器学习", "深度学习", "神经网络", "区块链", "云计算"]
        if any(term in data_lower for term in common_terms):
            risks.append({
                "type": "novelty_common_tech",
                "severity": "medium",
                "description": "技术方案包含通用技术术语，需要明确具体的创新实现细节",
                "category": "technical",
                "mitigation": "重点描述与通用技术结合的具体创新点和技术效果",
            })

        return risks

    def _analyze_inventive_step_risks(self, tech_data: str) -> List[Dict]:
        """分析创造性风险"""
        risks = []
        data_lower = tech_data.lower()

        # 检查技术效果描述
        if "效果" not in data_lower and "advantage" not in data_lower and "有益" not in data_lower:
            risks.append({
                "type": "inventive_step_no_effects",
                "severity": "high",
                "description": "缺少技术效果的描述，可能影响创造性评估",
                "category": "technical",
                "mitigation": "详细描述技术方案带来的具体技术效果和有益效果",
            })

        return risks

    def _analyze_prior_art_risks(self, prior_art_refs: str) -> List[Dict]:
        """分析现有技术风险"""
        risks = []

        try:
            refs = json.loads(prior_art_refs) if isinstance(prior_art_refs, str) else prior_art_refs
            if isinstance(refs, list) and len(refs) > 5:
                risks.append({
                    "type": "prior_art_high_volume",
                    "severity": "medium",
                    "description": f"发现 {len(refs)} 篇相关现有技术，需要仔细甄别最接近的对比文件",
                    "category": "search",
                    "mitigation": "筛选最相关的3-5篇对比文件进行深度比对分析",
                })
        except (json.JSONDecodeError, TypeError):
            pass

        return risks

    def _analyze_support_risks(self, tech_data: str) -> List[Dict]:
        """分析支持性风险（权利要求是否得到说明书支持）"""
        risks = []
        data_lower = tech_data.lower()

        # 检查实施例数量
        embodiment_count = len(re.findall(r"实施例|embodiment", data_lower))
        if embodiment_count < 2:
            risks.append({
                "type": "support_insufficient_embodiments",
                "severity": "medium",
                "description": "实施例数量可能不足，可能影响权利要求的支持性",
                "category": "drafting",
                "mitigation": "增加多个不同角度的实施例，覆盖权利要求的全部技术特征",
            })

        return risks

    def _generate_risk_matrix(self, risks: List[Dict]) -> Dict[str, int]:
        """生成风险矩阵统计"""
        matrix = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for risk in risks:
            matrix[risk["severity"]] = matrix.get(risk["severity"], 0) + 1
        return matrix

    def _generate_mitigation_priorities(self, risks: List[Dict]) -> List[str]:
        """生成缓解优先级建议"""
        # 按严重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_risks = sorted(risks, key=lambda r: severity_order.get(r["severity"], 99))

        return [
            f"[{risk['severity'].upper()}] {risk['description']} -> {risk['mitigation']}"
            for risk in sorted_risks
        ]
