"""Creative Thinking Tool - 创意思维工具."""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


class CreativeThinkingTool(HermesTool):
    """创意思维工具"""
    name = "creative_thinking"
    description = "根据技术文本提取候选发散方向；创新价值和采用与否由 Agent 判断"

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
            },
        )

    async def execute(self, tech_description: str, **kwargs) -> Dict[str, Any]:
        """执行创意激发：提供结构化发散方向，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Generating creative patent ideas")
        text = tech_description or ""
        terms = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", text)
        key_terms = list(dict.fromkeys(term for term in terms if len(term) >= 2))[:8]
        subject = "、".join(key_terms[:3]) or "核心技术对象"
        data = {
            "alternative_embodiments": [
                {"idea": f"围绕{subject}的输入参数获取方式扩展", "technical_approach": "梳理可由传感器、用户输入、业务数据或系统状态提供的输入来源", "agent_decision_required": "是否纳入专利方案"},
                {"idea": f"围绕{subject}的核心处理规则或模型扩展", "technical_approach": "将核心处理拆分为可验证的规则、模型、映射关系或控制策略", "agent_decision_required": "是否构成核心创新点"},
                {"idea": f"围绕{subject}的系统模块化实现", "technical_approach": "把方法步骤对应到采集、处理、执行、反馈或输出模块", "agent_decision_required": "是否需要形成系统/装置权利要求"},
            ],
            "cross_domain_applications": [
                "与当前输入术语相关的设备端实现",
                "与当前输入术语相关的软件系统实现",
                "与当前输入术语相关的端云协同实现",
            ],
            "improvement_directions": [
                {"direction": "输入数据质量控制", "potential_benefit": "提高处理结果稳定性和可重复性", "feasibility": "medium"},
                {"direction": "异常状态处理与反馈闭环", "potential_benefit": "提高系统鲁棒性并形成从属保护点", "feasibility": "medium"},
            ],
            "combination_innovations": [f"{subject}+输入获取+核心处理+结果输出闭环"],
            "strategic_insights": "Agent 应基于当前技术事实判断保护核心，不得套用历史案例的技术主题。",
            "requires_agent_judgment": [
                "候选方向是否真实来自当前技术事实",
                "是否需要进一步向用户确认",
                "是否进入后续需求分析或检索阶段",
            ],
            "source_preview": text[:300],
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
