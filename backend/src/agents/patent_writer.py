from typing import List
import json

from loguru import logger

from .base import BaseHermesAgent, AgentRole
from ..models.domain import (
    PatentTask,
    PatentDraft,
    Claim,
    DescriptionSection,
    FinalizedPatent,
)
from ..prompts.templates import PROMPTS


class PatentWriterAgent(BaseHermesAgent):
    """专利撰写Agent - 基于Hermes的专利申请文件生成专家"""

    def __init__(self):
        super().__init__(
            name="专利撰写Agent",
            description="基于结构化技术需求和检索分析报告，生成符合专利法规范的申请文件",
            role=AgentRole.SPECIALIST,
        )
        # 初始化 Hermes Agent
        self._init_hermes_agent(
            system_prompt="你是资深专利代理人，擅长撰写符合专利法规范的申请文件。",
            tools=["search_knowledge_base", "validate_json"],
        )

    async def _execute(self, task: PatentTask) -> PatentTask:
        """执行专利撰写"""
        self.context.add_event("开始撰写专利申请文件", "progress")

        if not task.requirement_doc:
            raise ValueError("需求分析文档不存在，无法撰写")

        # 1. 从知识库获取写作范例和风格参考
        exemplars = self.context.get_exemplars(task.requirement_doc.tech_field)
        similar_patents = self.context.get_similar_patents(top_k=3)

        style_references = exemplars + similar_patents
        if style_references:
            self.context.add_event(
                f"加载 {len(style_references)} 篇专利作为写作风格参考",
                "info",
                {"references": [p.title for p in style_references]},
            )

        # 2. 提取写作风格指南
        style_guide = self._extract_style_guide(style_references)

        # 3. 分步撰写各个部分
        # 3.1 撰写权利要求书
        self.context.add_event("正在撰写权利要求书", "progress")
        claims = await self._write_claims(task, style_guide)

        # 3.2 撰写说明书
        self.context.add_event("正在撰写说明书", "progress")
        description_sections = await self._write_description(task, style_guide)

        # 3.3 撰写摘要
        self.context.add_event("正在撰写摘要", "progress")
        abstract = await self._write_abstract(task)

        # 4. 组装完整文档
        patent_draft = PatentDraft(
            title=self._generate_title(task),
            technical_field=task.requirement_doc.tech_field,
            background_art=description_sections["background"],
            summary_of_invention=description_sections["summary"],
            description_of_drawings=description_sections.get("drawings"),
            detailed_description=description_sections["detailed"],
            claims=claims,
            abstract=abstract,
            reference_patent_style_ids=[p.patent_id for p in style_references],
        )

        # 5. 更新任务
        task.draft_doc = patent_draft
        self.context.add_event(
            f"专利文件撰写完成，共 {len(claims)} 项权利要求，总字数: {patent_draft.word_count}",
            "success",
        )

        return task

    def _extract_style_guide(self, reference_patents: List[FinalizedPatent]) -> str:
        """从参考专利中提取写作风格指南"""
        if not reference_patents:
            return "遵循标准专利写作规范，使用正式、严谨的法律语言"

        # 分析参考专利的写作特征
        features = []
        for p in reference_patents[:2]:
            if p.writing_patterns:
                features.extend(p.writing_patterns[:5])

        if not features:
            features = [
                "使用'本发明涉及...'开头",
                "独立权利要求采用前序+特征的结构",
                "技术术语保持一致定义",
            ]

        return "\n".join([f"- {f}" for f in features])

    async def _write_claims(self, task: PatentTask, style_guide: str) -> List[Claim]:
        """撰写权利要求书"""
        prompt = PROMPTS["patent_writer"]["claims"].format(
            key_features="\n".join([
                f"{i+1}. {f.name}: {f.description}"
                for i, f in enumerate(task.requirement_doc.key_features)
            ]),
            technical_problem=task.requirement_doc.technical_problem,
            writing_tips=style_guide,
            retrieval_suggestions="\n".join(
                task.retrieval_report.writing_recommendations
                if task.retrieval_report else []
            ),
        )

        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["patent_writer"]["system"],
        )

        return self._parse_claims_response(response)

    def _parse_claims_response(self, response: str) -> List[Claim]:
        """解析权利要求响应"""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            data = json.loads(response[json_start:json_end])

            claims = []
            for c_data in data.get("claims", []):
                claim = Claim(
                    claim_number=int(c_data.get("number", len(claims) + 1)),
                    claim_type=c_data.get("type", "independent"),
                    content=c_data.get("content", ""),
                    dependencies=c_data.get("dependencies", []),
                    category=c_data.get("category"),
                )
                claims.append(claim)

            return claims
        except Exception as e:
            logger.warning(f"解析权利要求失败: {e}")
            return [
                Claim(
                    claim_number=1,
                    claim_type="independent",
                    content="一种基于人工智能的智能对话方法，其特征在于包括以下步骤...",
                    category="method",
                )
            ]

    async def _write_description(self, task: PatentTask, style_guide: str) -> dict:
        """撰写说明书各部分"""
        prompt = PROMPTS["patent_writer"]["description"].format(
            tech_field=task.requirement_doc.tech_field,
            background_problem=task.requirement_doc.technical_problem,
            technical_solution=task.requirement_doc.technical_solution_summary,
            key_features="\n".join([
                f"- {f.name}: {f.description}"
                for f in task.requirement_doc.key_features
            ]),
            beneficial_effects="\n".join(task.requirement_doc.beneficial_effects),
            writing_tips=style_guide,
        )

        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["patent_writer"]["system"],
        )

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            data = json.loads(response[json_start:json_end])

            return {
                "background": DescriptionSection(
                    section_name="背景技术",
                    content=data.get("background_art", ""),
                    word_count=len(data.get("background_art", "")),
                ),
                "summary": DescriptionSection(
                    section_name="发明内容",
                    content=data.get("summary", ""),
                    word_count=len(data.get("summary", "")),
                ),
                "detailed": DescriptionSection(
                    section_name="具体实施方式",
                    content=data.get("detailed_description", ""),
                    word_count=len(data.get("detailed_description", "")),
                ),
            }
        except Exception as e:
            logger.warning(f"解析说明书失败: {e}")
            return {
                "background": DescriptionSection(
                    section_name="背景技术",
                    content="本发明涉及人工智能技术领域...",
                    word_count=0,
                ),
                "summary": DescriptionSection(
                    section_name="发明内容",
                    content="本发明的目的在于提供一种...",
                    word_count=0,
                ),
                "detailed": DescriptionSection(
                    section_name="具体实施方式",
                    content="下面结合具体实施例对本发明做进一步说明...",
                    word_count=0,
                ),
            }

    async def _write_abstract(self, task: PatentTask) -> str:
        """撰写摘要"""
        prompt = f"""
        请为以下技术发明撰写150-300字的专利摘要：

        技术领域：{task.requirement_doc.tech_field}
        核心原理：{task.requirement_doc.core_principle}
        有益效果：{', '.join(task.requirement_doc.beneficial_effects)}

        摘要应包括：技术领域、要解决的技术问题、技术方案要点、有益效果。
        """

        response = await self._call_hermes(prompt=prompt, system_prompt="你是专业的专利代理人")
        return response.strip()

    def _generate_title(self, task: PatentTask) -> str:
        """生成专利标题"""
        feature_names = [f.name for f in task.requirement_doc.key_features[:2]]
        feature_str = "与".join(feature_names) if feature_names else "智能"
        return f"一种{feature_str}的方法和系统"
