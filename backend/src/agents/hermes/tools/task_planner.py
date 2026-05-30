"""
TaskPlannerTool - 任务规划工具
帮助 CEO Agent 制定专利申请工作计划
"""
from datetime import datetime
from typing import Any, Dict

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
