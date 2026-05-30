"""
Agent Selector Tool - Agent 选择路由工具
帮助 CEO Agent 选择最适合处理当前任务的专业 Agent
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)

# Agent 能力映射
AGENT_CAPABILITIES = {
    "patent.requirement_analyst.v1": {
        "name": "需求分析师",
        "keywords": ["需求", "分析", "创新点", "技术描述", "结构化", "IPC", "分类"],
        "strengths": "将非结构化技术描述转化为标准化专利需求文档",
    },
    "patent.retrieval_analyst.v1": {
        "name": "检索分析师",
        "keywords": ["检索", "现有技术", "新颖性", "创造性", "对比", "prior art"],
        "strengths": "现有技术检索、专利性评估和风险识别",
    },
    "patent.writer.v1": {
        "name": "专利撰写师",
        "keywords": ["撰写", "权利要求", "说明书", "摘要", "claim", "draft"],
        "strengths": "撰写符合专利法规范的高质量申请文件",
    },
    "patent.quality_reviewer.v1": {
        "name": "质量审查师",
        "keywords": ["审查", "质量", "合规", "审查意见", "修改", "review"],
        "strengths": "形式合规、权利要求质量、说明书质量等全面审查",
    },
    "patent.brainstorm_partner.v1": {
        "name": "头脑风暴伙伴",
        "keywords": ["创意", "头脑风暴", "讨论", "探索", "方向", "brainstorm"],
        "strengths": "创意探讨、拓展保护方向、激发发明思路",
    },
}


class AgentSelectorTool(HermesTool):
    """Agent 选择路由工具"""
    name = "agent_selector"
    description = "根据任务描述选择最适合的专业 Agent 来处理任务"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "task_description": HermesToolParameter(
                    type="string",
                    description="需要处理的任务描述",
                    required=True,
                ),
                "exclude_agents": HermesToolParameter(
                    type="string",
                    description="排除的 Agent ID（逗号分隔）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, task_description: str, exclude_agents: str = "", **kwargs
    ) -> Dict[str, Any]:
        """根据任务描述选择 Agent"""
        logger.info("Selecting agent for task", task=task_description[:50])

        excluded = set(exclude_agents.split(",")) if exclude_agents else set()
        task_lower = task_description.lower()

        # 基于关键词匹配计算每个 Agent 的相关度
        scores = {}
        for agent_id, info in AGENT_CAPABILITIES.items():
            if agent_id in excluded:
                continue
            score = sum(1 for kw in info["keywords"] if kw in task_lower)
            scores[agent_id] = score

        if not scores:
            return {
                "selected_agent": None,
                "reasoning": "所有 Agent 已被排除",
                "tool": self.name,
            }

        # 选择得分最高的
        best_agent = max(scores, key=scores.get)
        best_info = AGENT_CAPABILITIES[best_agent]

        return {
            "selected_agent": best_agent,
            "agent_name": best_info["name"],
            "reasoning": f"任务与'{best_info['name']}'的能力最匹配: {best_info['strengths']}",
            "confidence": min(scores[best_agent] / 3.0, 1.0),
            "all_scores": {
                AGENT_CAPABILITIES[k]["name"]: v
                for k, v in sorted(scores.items(), key=lambda x: -x[1])
            },
            "tool": self.name,
        }
