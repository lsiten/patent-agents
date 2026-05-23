from typing import List
import json

from loguru import logger

from .base import BaseHermesAgent, AgentRole
from ..models.domain import PatentTask, RequirementDoc, KeyFeature
from ..models.enums import PatentType
from ..prompts.templates import PROMPTS


class RequirementAnalystAgent(BaseHermesAgent):
    """需求分析Agent - 基于Hermes的技术需求结构化专家"""

    def __init__(self):
        super().__init__(
            name="需求分析Agent",
            description="深度理解技术描述，提取关键创新点，判定专利类型，生成结构化需求文档",
            role=AgentRole.SPECIALIST,
        )
        # 初始化 Hermes Agent
        self._init_hermes_agent(
            system_prompt="你是专业的专利代理人，擅长将非结构化技术描述转化为标准化的专利申请需求文档。",
            tools=["search_knowledge_base", "validate_json"],
        )

    async def _execute(self, task: PatentTask) -> PatentTask:
        """执行需求分析"""
        self.context.add_event("开始分析技术描述", "progress")

        # 1. 从知识库获取相似专利作为参考
        similar_patents = self.context.get_similar_patents(top_k=3)
        if similar_patents:
            self.context.add_event(
                f"找到 {len(similar_patents)} 篇相似专利作为参考",
                "info",
                {"patents": [p.title for p in similar_patents]}
            )

        # 2. 构建Prompt
        prompt = self._build_prompt(task.tech_description, similar_patents)

        # 3. 调用LLM
        response = await self._call_hermes(
            prompt=prompt,
            system_prompt=PROMPTS["requirement_analyst"]["system"],
        )

        # 4. 解析响应
        requirement_doc = self._parse_response(response)

        # 5. 检查信息缺口
        if requirement_doc.information_gaps:
            self.context.add_event(
                f"发现 {len(requirement_doc.information_gaps)} 个信息缺口，需要用户补充",
                "warning",
                {"gaps": requirement_doc.information_gaps},
            )

        # 6. 更新任务
        task.requirement_doc = requirement_doc
        self.context.add_event(
            f"需求分析完成，推荐专利类型: {requirement_doc.patent_type_recommendation}",
            "success",
        )

        return task

    def _build_prompt(self, tech_description: str, similar_patents: List) -> str:
        """构建Prompt"""
        examples_section = ""
        if similar_patents:
            examples = "\n".join([
                f"- {p.title} (领域: {p.tech_field})"
                for p in similar_patents
            ])
            examples_section = f"""
            参考相似专利：
            {examples}

            请参考上述专利的技术领域分类和标准化术语。
            """

        return PROMPTS["requirement_analyst"]["user"].format(
            tech_description=tech_description,
            examples_section=examples_section,
        )

    def _parse_response(self, response: str) -> RequirementDoc:
        """解析LLM响应为结构化需求文档"""
        try:
            # 尝试提取JSON部分
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                data = json.loads(response)

            # 转换为KeyFeature对象
            key_features = [
                KeyFeature(**f) for f in data.get("key_features", [])
            ]

            return RequirementDoc(
                tech_field=data.get("tech_field", ""),
                core_principle=data.get("core_principle", ""),
                application_scenarios=data.get("application_scenarios", []),
                technical_problem=data.get("technical_problem", ""),
                technical_solution_summary=data.get("technical_solution_summary", ""),
                key_features=key_features,
                patent_type_recommendation=PatentType(data.get("patent_type", "invention")),
                recommendation_rationale=data.get("recommendation_rationale", ""),
                beneficial_effects=data.get("beneficial_effects", []),
                information_gaps=data.get("information_gaps", []),
                analysis_confidence=data.get("confidence", 0.8),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"解析需求分析响应失败，使用默认结构: {e}")
            # 降级处理 - 创建基础结构
            return RequirementDoc(
                tech_field="未确定",
                core_principle="待补充",
                application_scenarios=["待补充"],
                technical_problem="待补充",
                technical_solution_summary="待补充",
                key_features=[],
                patent_type_recommendation=PatentType.INVENTION,
                recommendation_rationale="自动解析失败，默认推荐发明专利",
                beneficial_effects=[],
                information_gaps=["需要人工审核技术描述"],
                analysis_confidence=0.3,
            )
