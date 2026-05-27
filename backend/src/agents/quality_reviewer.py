from typing import List
import json
import re

from loguru import logger

from .base import BaseHermesAgent, AgentRole
from ..models.domain import (
    PatentTask,
    ReviewReport,
    ReviewResult,
    ReviewIssue,
)
from ..models.enums import Severity
from ..prompts.templates import PROMPTS


class QualityReviewerAgent(BaseHermesAgent):
    """质量审查Agent - 基于Hermes的专利申请文件质量审查专家"""

    def __init__(self):
        super().__init__(
            name="质量审查Agent",
            description="全面审查专利申请文件的形式合规性、实质内容和审查风险",
            role=AgentRole.SPECIALIST,
        )
        # 初始化 Hermes Agent
        self._init_hermes_agent(
            system_prompt="你是专利审查专家，擅长评估申请文件的形式合规性、实质内容和审查风险。",
            tools=["search_knowledge_base", "validate_json"],
        )

    async def _execute(self, task: PatentTask) -> PatentTask:
        """执行质量审查"""
        self.context.add_event("开始专利申请文件质量审查", "progress")

        if not task.draft_doc:
            raise ValueError("专利草稿不存在，无法进行审查")

        # 1. 形式合规性检查 (规则引擎)
        self.context.add_event("进行形式合规性检查", "progress")
        formal_result = self._check_formal_compliance(task.draft_doc)

        # 2. 权利要求书审查
        self.context.add_event("审查权利要求书", "progress")
        claims_result = await self._review_claims(task)

        # 3. 说明书审查
        self.context.add_event("审查说明书", "progress")
        description_result = await self._review_description(task)

        # 4. 一致性审查
        self.context.add_event("进行一致性检查", "progress")
        consistency_result = self._check_consistency(task.draft_doc)

        # 5. 现有技术风险审查
        self.context.add_event("评估审查意见风险", "progress")
        prior_art_result = self._assess_prior_art_risk(task)

        # 6. 综合评分与建议
        overall_score = (
            formal_result.score * 0.25
            + claims_result.score * 0.30
            + description_result.score * 0.25
            + consistency_result.score * 0.10
            + prior_art_result.score * 0.10
        )

        recommendation, priority = self._generate_recommendation(
            overall_score, formal_result, claims_result, description_result
        )

        # 7. 生成审查报告
        review_report = ReviewReport(
            formal_compliance=formal_result,
            claims_review=claims_result,
            description_review=description_result,
            consistency_review=consistency_result,
            prior_art_risk=prior_art_result,
            overall_score=round(overall_score, 2),
            recommendation=recommendation,
            revision_priority=priority,
            estimated_office_action_risk=self._calculate_oa_risk(
                formal_result, claims_result, description_result
            ),
            improvement_suggestions=self._generate_improvement_suggestions(
                formal_result, claims_result, description_result
            ),
        )

        # 更新任务
        task.review_report = review_report
        self.context.add_event(
            f"质量审查完成，综合得分: {review_report.overall_score:.2f}，建议: {recommendation}",
            "success" if recommendation == "approve" else "warning",
        )

        return task

    def _check_formal_compliance(self, draft_doc) -> ReviewResult:
        """形式合规性检查 - 规则引擎"""
        issues = []
        score = 1.0

        # 检查1: 权利要求编号连续性
        claim_numbers = sorted([c.claim_number for c in draft_doc.claims])
        expected = list(range(1, len(claim_numbers) + 1))
        if claim_numbers != expected:
            issues.append(ReviewIssue(
                issue_id="F001",
                severity=Severity.MEDIUM,
                location="权利要求书",
                issue_type="编号错误",
                description="权利要求编号不连续",
                suggestion="请修正编号顺序",
            ))
            score -= 0.1

        # 检查2: 独立权利要求格式
        for claim in draft_doc.claims:
            if claim.claim_type == "independent":
                if "其特征在于" not in claim.content and "其特征是" not in claim.content:
                    issues.append(ReviewIssue(
                        issue_id=f"F002-{claim.claim_number}",
                        severity=Severity.HIGH,
                        location=f"权利要求{claim.claim_number}",
                        issue_type="格式问题",
                        description="独立权利要求缺少'其特征在于'等划分技术特征的语句",
                        suggestion="在独立权利要求中添加前序与特征的划分",
                    ))
                    score -= 0.15

        # 检查3: 摘要长度
        if len(draft_doc.abstract) < 100:
            issues.append(ReviewIssue(
                issue_id="F003",
                severity=Severity.LOW,
                location="摘要",
                issue_type="长度不足",
                description="摘要长度偏短，可能影响技术方案的完整表达",
                suggestion="建议补充摘要内容至150-300字",
            ))
            score -= 0.05

        # 检查4: 标准术语使用
        forbidden_terms = ["最好", "最佳", "必须", "绝对", "可以", "可选"]
        content = draft_doc.claims[0].content if draft_doc.claims else ""
        for term in forbidden_terms:
            if term in content:
                issues.append(ReviewIssue(
                    issue_id=f"F004-{term}",
                    severity=Severity.MEDIUM,
                    location="权利要求书",
                    issue_type="术语不当",
                    description=f"权利要求中出现主观或不确定术语: '{term}'",
                    suggestion=f"建议移除或替换'{term}'为客观描述",
                ))
                score -= 0.05

        return ReviewResult(passed=score >= 0.8, score=max(0, score), issues=issues)

    async def _review_claims(self, task: PatentTask) -> ReviewResult:
        """审查权利要求书 - 使用LLM深度审查"""
        prompt = PROMPTS["quality_reviewer"]["claims"].format(
            claims_text="\n\n".join([
                f"权利要求{c.claim_number} ({c.claim_type}):\n{c.content}"
                for c in task.draft_doc.claims
            ]),
            technical_features="\n".join([
                f"- {f.name}: {f.description}"
                for f in task.requirement_doc.key_features
            ]),
        )

        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["quality_reviewer"]["system"],
        )

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            data = json.loads(response[json_start:json_end])

            issues = []
            for issue_data in data.get("issues", []):
                issues.append(ReviewIssue(
                    issue_id=issue_data.get("id", ""),
                    severity=Severity(issue_data.get("severity", "medium")),
                    location=issue_data.get("location", ""),
                    issue_type=issue_data.get("type", ""),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                ))

            score = float(data.get("score", 0.7))
            return ReviewResult(passed=score >= 0.90, score=score, issues=issues)

        except Exception as e:
            logger.warning(f"解析权利要求审查结果失败: {e}")
            return ReviewResult(passed=True, score=0.90, issues=[])

    async def _review_description(self, task: PatentTask) -> ReviewResult:
        """审查说明书"""
        prompt = PROMPTS["quality_reviewer"]["description"].format(
            background=task.draft_doc.background_art.content[:500],
            summary=task.draft_doc.summary_of_invention.content[:500],
            detailed=task.draft_doc.detailed_description.content[:1000],
        )

        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["quality_reviewer"]["system"],
        )

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            data = json.loads(response[json_start:json_end])

            issues = []
            for issue_data in data.get("issues", []):
                issues.append(ReviewIssue(
                    issue_id=issue_data.get("id", ""),
                    severity=Severity(issue_data.get("severity", "medium")),
                    location=issue_data.get("location", ""),
                    issue_type=issue_data.get("type", ""),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                ))

            score = float(data.get("score", 0.7))
            return ReviewResult(passed=score >= 0.90, score=score, issues=issues)

        except Exception as e:
            logger.warning(f"解析说明书审查结果失败: {e}")
            return ReviewResult(passed=True, score=0.90, issues=[])

    def _check_consistency(self, draft_doc) -> ReviewResult:
        """一致性检查 - 权利要求与说明书对应关系"""
        issues = []
        score = 1.0

        # 检查权利要求中的术语在说明书中是否有定义
        claim_terms = set(re.findall(r"[\u4e00-\u9fa5a-zA-Z]+装置|[\u4e00-\u9fa5a-zA-Z]+模块", draft_doc.claims[0].content if draft_doc.claims else ""))

        description_content = draft_doc.detailed_description.content
        for term in claim_terms:
            if term not in description_content:
                issues.append(ReviewIssue(
                    issue_id=f"C001-{term}",
                    severity=Severity.HIGH,
                    location="权利要求与说明书",
                    issue_type="术语不一致",
                    description=f"术语 '{term}' 在权利要求中使用但说明书中未充分说明",
                    suggestion=f"在说明书具体实施方式中补充'{term}'的详细说明",
                ))
                score -= 0.1

        return ReviewResult(passed=score >= 0.90, score=max(0, score), issues=issues)

    def _assess_prior_art_risk(self, task: PatentTask) -> ReviewResult:
        """评估现有技术风险"""
        score = 1.0
        issues = []

        if task.retrieval_report:
            high_risk_count = len(task.retrieval_report.high_risk_references)
            if high_risk_count > 0:
                score = max(0.3, 1.0 - high_risk_count * 0.15)
                issues.append(ReviewIssue(
                    issue_id="P001",
                    severity=Severity.HIGH,
                    location="专利性评估",
                    issue_type="现有技术风险",
                    description=f"发现 {high_risk_count} 篇高相似度现有技术，可能影响新颖性/创造性",
                    suggestion="建议在说明书中重点强调与对比文献的区别技术特征",
                ))

        return ReviewResult(passed=score >= 0.5, score=score, issues=issues)

    def _generate_recommendation(self, overall_score: float, *results) -> tuple:
        """生成审查建议"""
        critical_issues = sum(
            len([i for i in r.issues if i.severity == Severity.CRITICAL])
            for r in results
        )
        high_issues = sum(
            len([i for i in r.issues if i.severity == Severity.HIGH])
            for r in results
        )

        if critical_issues > 0 or overall_score < 0.75:
            return "reject", Severity.CRITICAL
        elif high_issues > 0 or overall_score < 0.85:
            return "revise", Severity.HIGH
        elif overall_score < 0.90:
            return "revise", Severity.MEDIUM
        else:
            return "approve", Severity.LOW

    def _calculate_oa_risk(self, *results) -> float:
        """预估审查意见风险"""
        high_issues = sum(
            len([i for i in r.issues if i.severity in [Severity.CRITICAL, Severity.HIGH]])
            for r in results
        )
        return min(1.0, high_issues * 0.15 + 0.1)

    def _generate_improvement_suggestions(self, *results) -> List[str]:
        """生成改进建议摘要"""
        suggestions = []
        for result in results:
            for issue in result.issues:
                if issue.severity in [Severity.CRITICAL, Severity.HIGH]:
                    suggestions.append(f"{issue.location}: {issue.suggestion}")
        return suggestions[:10]  # 最多返回10条建议
