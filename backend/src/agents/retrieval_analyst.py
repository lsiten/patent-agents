from typing import List
import json

from loguru import logger

from .base import BaseHermesAgent, AgentRole
from ..models.domain import (
    PatentTask,
    RetrievalReport,
    PriorArtReference,
    SearchQuery,
    ReviewResult,
)
from ..models.enums import Rating
from ..prompts.templates import PROMPTS


class RetrievalAnalystAgent(BaseHermesAgent):
    """检索分析Agent - 基于Hermes的专利性评估专家"""

    def __init__(self):
        super().__init__(
            name="检索分析Agent",
            description="基于结构化技术需求排查现有技术，评估发明的新颖性、创造性、实用性",
            role=AgentRole.SPECIALIST,
        )
        # 初始化 Hermes Agent
        self._init_hermes_agent(
            system_prompt="你是专利检索专家，擅长分析技术方案的新颖性、创造性和实用性。",
            tools=["search_knowledge_base", "search_patents", "validate_json"],
        )

    async def _execute(self, task: PatentTask) -> PatentTask:
        """执行检索分析"""
        self.context.add_event("开始专利性检索分析", "progress")

        if not task.requirement_doc:
            raise ValueError("需求分析文档不存在，无法进行检索分析")

        # 1. 构建检索关键词
        search_keywords = self._build_search_keywords(task.requirement_doc)
        self.context.add_event(f"构建检索关键词: {search_keywords}", "info")

        # 2. 调用多数据源并行检索
        search_query = SearchQuery(
            query=" ".join(search_keywords[:5]),  # 使用前5个关键词
            tech_field=task.requirement_doc.tech_field,
            max_results=20,
        )

        prior_arts = await self.context.data_sources.search_all(search_query)
        self.context.add_event(f"检索完成，找到 {len(prior_arts)} 篇现有技术", "info")

        # 3. 提取高风险对比文献
        high_risk_arts = [p for p in prior_arts if p.similarity_score >= 0.7]
        if high_risk_arts:
            self.context.add_event(
                f"发现 {len(high_risk_arts)} 篇高相似度对比文献",
                "warning",
                {"patents": [p.reference_id for p in high_risk_arts]},
            )

        # 4. LLM分析专利性
        prompt = self._build_prompt(task, prior_arts)
        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["retrieval_analyst"]["system"],
        )

        # 5. 解析生成报告
        retrieval_report = self._parse_response(response, prior_arts)
        retrieval_report.retrieval_databases = ["uspto", "cnipa", "epo", "google_patents", "arxiv"]
        retrieval_report.retrieval_keywords = search_keywords

        # 6. 更新任务
        task.retrieval_report = retrieval_report
        self.context.add_event(
            f"专利性评估完成，综合评级: {retrieval_report.overall_patentability}",
            "success",
        )

        return task

    def _build_search_keywords(self, requirement_doc) -> List[str]:
        """构建检索关键词"""
        keywords = []

        # 从技术领域提取
        keywords.extend(requirement_doc.tech_field.split())

        # 从关键特征提取
        for feature in requirement_doc.key_features:
            keywords.extend(feature.name.split())

        # 从核心原理提取
        keywords.extend(requirement_doc.core_principle.split()[:10])

        # 去重并过滤停用词
        stop_words = {"的", "是", "在", "和", "与", "或", "一种", "该", "其", "用于", "可以", "通过"}
        keywords = [k for k in keywords if k not in stop_words and len(k) > 1]

        return list(set(keywords))[:20]

    def _build_prompt(self, task: PatentTask, prior_arts: List[PriorArtReference]) -> str:
        """构建分析Prompt"""
        # 格式化对比文献
        prior_art_text = ""
        for i, art in enumerate(prior_arts[:10], 1):  # 最多取10篇
            prior_art_text += f"""
            [{i}] {art.reference_id} - {art.title}
                摘要: {art.abstract[:200]}...
                相似度: {art.similarity_score:.2f}
            """

        if not prior_art_text:
            prior_art_text = "未检索到相关现有技术"

        return PROMPTS["retrieval_analyst"]["user"].format(
            tech_field=task.requirement_doc.tech_field,
            key_features="\n".join([
                f"- {f.name}: {f.description}"
                for f in task.requirement_doc.key_features
            ]),
            core_principle=task.requirement_doc.core_principle,
            prior_arts=prior_art_text,
        )

    def _parse_response(
        self,
        response: str,
        prior_arts: List[PriorArtReference],
    ) -> RetrievalReport:
        """解析LLM响应"""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                data = json.loads(response)

            return RetrievalReport(
                novelty_assessment=Rating(data.get("novelty", "medium")),
                novelty_rationale=data.get("novelty_rationale", ""),
                inventive_step_assessment=Rating(data.get("inventive_step", "medium")),
                inventive_step_rationale=data.get("inventive_step_rationale", ""),
                utility_assessment=Rating(data.get("utility", "high")),
                utility_rationale=data.get("utility_rationale", ""),
                overall_patentability=Rating(data.get("overall_patentability", "medium")),
                overall_confidence=data.get("confidence", 0.7),
                prior_art_found=prior_arts,
                high_risk_references=[p for p in prior_arts if p.similarity_score >= 0.7],
                writing_recommendations=data.get("writing_recommendations", []),
                claim_strategy_recommendations=data.get("claim_strategy_recommendations", []),
                risk_factors=data.get("risk_factors", []),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"解析检索分析响应失败，使用默认结构: {e}")
            return RetrievalReport(
                novelty_assessment=Rating.MEDIUM,
                novelty_rationale="自动解析失败，需要人工审核",
                inventive_step_assessment=Rating.MEDIUM,
                inventive_step_rationale="自动解析失败，需要人工审核",
                utility_assessment=Rating.HIGH,
                utility_rationale="",
                overall_patentability=Rating.MEDIUM,
                overall_confidence=0.5,
                prior_art_found=prior_arts,
                writing_recommendations=["请人工审查专利性后再进行撰写"],
                risk_factors=["自动检索分析失败，存在驳回风险"],
            )
