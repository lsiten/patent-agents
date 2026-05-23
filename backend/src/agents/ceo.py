from typing import Dict, Optional, List
from datetime import datetime
import json

from loguru import logger
from .base import BaseHermesAgent, AgentRole
from .requirement_analyst import RequirementAnalystAgent
from .retrieval_analyst import RetrievalAnalystAgent
from .patent_writer import PatentWriterAgent
from .quality_reviewer import QualityReviewerAgent
from ..models.enums import WorkflowState, AgentStatus
from ..models.domain import PatentTask
from ..core.workflow import get_state_machine


CEO_SYSTEM_PROMPT = """
你是专利申请多智能体系统的 CEO Orchestrator，负责全局流程调度、质量门控与跨 Agent 协同。

## 核心职责

1. **流程调度**
   - 根据当前工作流状态，决定下一步调用哪个专业 Agent
   - 管理状态转换，确保工作流按正确顺序执行
   - 监控各 Agent 执行进度与资源消耗

2. **质量门控**
   - 在每个阶段结束时进行质量评估
   - 未达标的阶段触发重新执行或迭代
   - 高风险任务及时终止并向用户说明

3. **冲突协调**
   - 解决 Agent 之间的输出不一致
   - 仲裁不同 Agent 的建议冲突
   - 确保最终输出的一致性和完整性

## 决策规则

| 当前状态 | 触发条件 | 下一状态 | 执行动作 |
|---------|---------|---------|---------|
| INITIAL | 用户提交技术描述 | REQUIREMENT_ANALYSIS | 调度需求分析 Agent |
| REQUIREMENT_ANALYSIS | 无信息缺口 | RETRIEVAL_ANALYSIS | 调度检索分析 Agent |
| REQUIREMENT_ANALYSIS | 发现信息缺口 | INITIAL | 向用户请求补充信息 |
| RETRIEVAL_ANALYSIS | 专利性良好 | WRITING | 调度专利撰写 Agent |
| RETRIEVAL_ANALYSIS | 专利性低 | FAILED | 终止流程，说明风险 |
| WRITING | 撰写完成 | REVIEWING | 调度质量审查 Agent |
| REVIEWING | 审查通过 | COMPLETED | 生成最终交付包 |
| REVIEWING | 审查不通过，迭代<3 | WRITING | 触发撰写迭代 |
| REVIEWING | 审查不通过，迭代≥3 | FAILED | 标记需人工审核 |

## 输出格式

请严格以 JSON 格式输出决策：
{
  "decision": "proceed|request_input|terminate|iterate",
  "next_state": "目标工作流状态",
  "target_agent": "要调度的Agent名称（如需要）",
  "reasoning": "决策推理说明",
  "quality_score": 0.0-1.0,
  "user_message": "给用户的消息（如需要）",
  "metadata": {"迭代次数": 0, "风险等级": "low|medium|high"}
}
"""


class CEOAgent(BaseHermesAgent):
    """CEO Orchestrator Agent - 基于 Hermes 的顶层统筹 Agent

    核心能力:
    - 子 Agent 孵化与管理
    - 智能流程调度与决策
    - 质量门控与风险评估
    - 跨 Agent 信息同步
    - 动态策略调整
    """

    def __init__(self):
        super().__init__(
            name="CEO Agent",
            description="专利申请多智能体系统顶层统筹，负责流程调度、质量门控与跨Agent协同",
            role=AgentRole.ORCHESTRATOR,
        )

        # 注册并初始化子 Agent
        self._register_sub_agents()

        # 初始化 Hermes Agent
        self._init_hermes_agent(
            system_prompt=CEO_SYSTEM_PROMPT,
            tools=["search_knowledge_base", "search_patents", "validate_json"],
        )

        # 状态管理
        self.state_machine = get_state_machine()
        self.execution_history: List[Dict] = []

    def _register_sub_agents(self):
        """注册并孵化所有专业子 Agent - Hermes 核心能力"""
        # 需求分析 Agent
        requirement_analyst = RequirementAnalystAgent()
        self.sub_agents["需求分析Agent"] = requirement_analyst

        # 检索分析 Agent
        retrieval_analyst = RetrievalAnalystAgent()
        self.sub_agents["检索分析Agent"] = retrieval_analyst

        # 专利撰写 Agent
        patent_writer = PatentWriterAgent()
        self.sub_agents["专利撰写Agent"] = patent_writer

        # 质量审查 Agent
        quality_reviewer = QualityReviewerAgent()
        self.sub_agents["质量审查Agent"] = quality_reviewer

        logger.info(f"[CEO Agent] 子 Agent 孵化完成，共 {len(self.sub_agents)} 个专业 Agent")

    async def _execute(self, task: PatentTask) -> PatentTask:
        """执行 CEO 统筹逻辑 - Hermes Orchestrator 模式"""
        self.context.add_event(
            "CEO Orchestrator 开始统筹任务",
            "progress",
            agent_name=self.name,
        )

        # 记录执行开始
        execution_record = {
            "start_time": datetime.now().isoformat(),
            "initial_state": task.current_state.value,
            "iterations": 0,
            "agent_executions": [],
        }

        try:
            # 主循环 - 直到任务完成或失败
            while task.current_state not in [
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
            ]:
                # 1. 获取当前状态的决策
                decision = await self._make_decision(task)

                # 2. 执行决策
                task = await self._execute_decision(task, decision, execution_record)

                # 3. 记录执行历史
                execution_record["agent_executions"].append(
                    {
                        "state": task.current_state.value,
                        "decision": decision,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                # 防止无限循环
                if execution_record["iterations"] > 10:
                    self.context.add_event(
                        "迭代次数超过限制，标记为需要人工审核",
                        "warning",
                        agent_name=self.name,
                    )
                    task.current_state = WorkflowState.FAILED
                    break

        except Exception as e:
            logger.exception(f"[CEO Agent] 统筹执行异常: {e}")
            self.context.add_event(
                f"统筹过程异常: {str(e)}",
                "error",
                agent_name=self.name,
            )
            task.current_state = WorkflowState.FAILED
            raise

        finally:
            execution_record["end_time"] = datetime.now().isoformat()
            execution_record["final_state"] = task.current_state.value
            self.execution_history.append(execution_record)

        # 任务完成，生成最终报告
        if task.current_state == WorkflowState.COMPLETED:
            await self._generate_final_report(task)

        return task

    async def _make_decision(self, task: PatentTask) -> Dict:
        """基于 Hermes 智能决策引擎生成下一步决策"""
        self.context.add_event(
            f"分析当前状态 [{task.current_state.value}]，生成决策...",
            "progress",
            agent_name=self.name,
        )

        # 构建决策上下文
        decision_context = {
            "task_id": task.task_id,
            "current_state": task.current_state.value,
            "tech_description": task.tech_description,
            "patent_type": task.patent_type_preference,
            "iteration_count": task.iteration_count,
            "has_requirement_doc": task.requirement_doc is not None,
            "has_retrieval_report": task.retrieval_report is not None,
            "has_patent_draft": task.draft_doc is not None,
            "has_review_report": task.review_report is not None,
        }

        # 调用 Hermes 进行智能决策
        decision_prompt = f"""
        基于以下任务上下文，生成下一步决策：

        任务上下文:
        {json.dumps(decision_context, ensure_ascii=False, indent=2)}

        请按照系统提示中的决策规则进行分析，并输出JSON格式的决策结果。
        """

        decision_result = await self._call_hermes(decision_prompt)

        try:
            json_start = decision_result.find("{")
            json_end = decision_result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                decision = json.loads(decision_result[json_start:json_end])
            else:
                decision = json.loads(decision_result)

            self.context.add_event(
                f"决策生成完成: {decision['decision']} -> {decision.get('next_state', 'N/A')}",
                "success",
                data=decision,
                agent_name=self.name,
            )
            return decision
        except json.JSONDecodeError as e:
            logger.warning(f"决策结果解析失败，使用默认决策: {e}")
            # 降级策略 - 使用简单的状态机规则
            return self._fallback_decision(task)

    def _fallback_decision(self, task: PatentTask) -> Dict:
        """降级决策策略 - 当 Hermes 决策失败时使用"""
        state_transitions = {
            WorkflowState.INITIAL: {
                "decision": "proceed",
                "next_state": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "target_agent": "需求分析Agent",
                "reasoning": "初始状态，开始需求分析",
                "quality_score": 1.0,
            },
            WorkflowState.REQUIREMENT_ANALYSIS: {
                "decision": "proceed",
                "next_state": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "target_agent": "检索分析Agent",
                "reasoning": "需求分析完成，进入专利性检索",
                "quality_score": 1.0,
            },
            WorkflowState.RETRIEVAL_ANALYSIS: {
                "decision": "proceed",
                "next_state": WorkflowState.WRITING.value,
                "target_agent": "专利撰写Agent",
                "reasoning": "检索分析完成，进入专利撰写阶段",
                "quality_score": 1.0,
            },
            WorkflowState.WRITING: {
                "decision": "proceed",
                "next_state": WorkflowState.REVIEWING.value,
                "target_agent": "质量审查Agent",
                "reasoning": "撰写完成，进入质量审查阶段",
                "quality_score": 1.0,
            },
            WorkflowState.REVIEWING: {
                "decision": "proceed",
                "next_state": WorkflowState.COMPLETED.value,
                "target_agent": None,
                "reasoning": "审查通过，任务完成",
                "quality_score": 1.0,
            },
        }

        return state_transitions.get(
            task.current_state,
            {
                "decision": "terminate",
                "next_state": WorkflowState.FAILED.value,
                "reasoning": "未知状态，终止任务",
                "quality_score": 0.0,
            },
        )

    async def _execute_decision(
        self,
        task: PatentTask,
        decision: Dict,
        execution_record: Dict,
    ) -> PatentTask:
        """执行 Hermes 生成的决策"""
        decision_type = decision.get("decision", "proceed")
        next_state = decision.get("next_state")
        target_agent_name = decision.get("target_agent")

        # 状态转换验证
        if next_state:
            try:
                target_state_enum = WorkflowState(next_state)
                if self.state_machine.transition(task.current_state, target_state_enum):
                    task.current_state = target_state_enum
            except ValueError:
                logger.warning(f"无效的目标状态: {next_state}")

        # 根据决策类型执行
        if decision_type == "proceed" and target_agent_name:
            # 委托给子 Agent 执行
            task = await self._execute_sub_agent(task, target_agent_name)
            execution_record["iterations"] += 1

        elif decision_type == "iterate":
            # 迭代模式 - 返回撰写阶段
            task.iteration_count += 1
            task.current_state = WorkflowState.WRITING
            self.context.add_event(
                f"触发第 {task.iteration_count} 次迭代优化",
                "warning",
                agent_name=self.name,
            )
            # 重新委托撰写 Agent
            task = await self._execute_sub_agent(task, "专利撰写Agent")

        elif decision_type == "request_input":
            # 请求用户输入 - 暂停任务
            self.context.add_event(
                f"需要用户补充信息: {decision.get('user_message', '')}",
                "warning",
                agent_name=self.name,
            )
            # 在实际场景中，这里会触发通知并暂停任务
            # 演示模式下继续执行

        elif decision_type == "terminate":
            # 终止任务
            task.current_state = WorkflowState.FAILED
            self.context.add_event(
                f"任务终止: {decision.get('reasoning', '')}",
                "error",
                agent_name=self.name,
            )

        return task

    async def _execute_sub_agent(self, task: PatentTask, agent_name: str) -> PatentTask:
        """委托子 Agent 执行 - Hermes 编排核心能力"""
        if agent_name not in self.sub_agents:
            raise ValueError(f"未知的子 Agent: {agent_name}")

        self.context.add_event(
            f"委托任务给 [{agent_name}]",
            "progress",
            agent_name=self.name,
        )

        sub_agent = self.sub_agents[agent_name]

        try:
            # 执行子 Agent
            result = await sub_agent.execute(task)

            # 同步子 Agent 的事件到 CEO 上下文
            for event in sub_agent.get_events():
                self.context.events.append(event)

            self.context.add_event(
                f"[{agent_name}] 执行完成",
                "success",
                agent_name=self.name,
            )

            return result

        except Exception as e:
            self.context.add_event(
                f"[{agent_name}] 执行异常: {str(e)}",
                "error",
                agent_name=self.name,
            )
            raise

    async def _generate_final_report(self, task: PatentTask):
        """生成最终交付报告 - Hermes 报告生成能力"""
        self.context.add_event(
            "生成最终专利申请交付包...",
            "progress",
            agent_name=self.name,
        )

        # 汇总各阶段输出
        final_report = {
            "task_id": task.task_id,
            "summary": {
                "total_iterations": task.iteration_count,
                "agents_involved": list(self.sub_agents.keys()),
                "patent_type": task.patent_type_preference,
            },
            "requirement_analysis": (
                task.requirement_doc.model_dump() if task.requirement_doc else None
            ),
            "patentability_assessment": (
                task.retrieval_report.model_dump() if task.retrieval_report else None
            ),
            "patent_draft": task.draft_doc.model_dump() if task.draft_doc else None,
            "quality_review": task.review_report.model_dump() if task.review_report else None,
            "next_steps": [
                "下载完整申请文件",
                "提交专利代理机构正式申请",
                "根据审查意见进行修改",
                "监控审查进度",
            ],
        }

        task.final_patent = final_report

        self.context.add_event(
            "专利申请交付包生成完成！",
            "success",
            data=final_report["summary"],
            agent_name=self.name,
        )

    def get_orchestrator_status(self) -> Dict:
        """获取 Orchestrator 状态"""
        return {
            "name": self.name,
            "status": self.status.value,
            "sub_agents": [
                {
                    "name": name,
                    "status": agent.get_status().value,
                    "description": agent.description,
                }
                for name, agent in self.sub_agents.items()
            ],
            "total_executions": len(self.execution_history),
        }


# 单例实例
_ceo_agent: Optional[CEOAgent] = None


def get_ceo_agent() -> CEOAgent:
    """获取 CEO Agent 单例"""
    global _ceo_agent
    if _ceo_agent is None:
        _ceo_agent = CEOAgent()
    return _ceo_agent
