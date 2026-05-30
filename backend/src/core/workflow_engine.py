"""
专利申请工作流编排引擎
协调 CEO Agent 与各专业 Agent 完成端到端专利申请流程

架构：CEO Agent 通过 dispatch_specialist 工具动态调度各专业 Agent，
本引擎仅负责状态管理、进度追踪和前端 API 兼容。
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field

from src.core.logging import get_logger
from src.core.events import (
    publish_event,
    AgentThinkingEvent,
    AgentToolCallStartEvent,
    AgentToolCallEndEvent,
    AgentDispatchEvent,
    AgentContentEvent,
)
from src.core.llm_client import LLMError


def _get_agent_factory():
    """返回 HermesAgentService 实例，用于工作流阶段调用 Agent。
    返回的 service 通过 run_conversation(profile_id, prompt) 执行对话。
    """
    from src.agents.hermes_agent_service import get_hermes_agent_service
    return get_hermes_agent_service()

logger = get_logger("workflow_engine")
T = TypeVar("T", bound=BaseModel)


class WorkflowState(str, Enum):
    """工作流状态枚举"""
    INITIALIZED = "initialized"
    # 头脑风暴阶段
    BRAINSTORMING = "brainstorming"
    # 需求分析阶段
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    # 检索分析阶段
    RETRIEVAL_ANALYSIS = "retrieval_analysis"
    # 专利撰写阶段
    PATENT_WRITING = "patent_writing"
    # 质量审查阶段
    QUALITY_REVIEW = "quality_review"
    # 迭代修正阶段
    ITERATION = "iteration"
    # 已完成
    COMPLETED = "completed"
    # 失败
    FAILED = "failed"
    # 用户取消
    CANCELLED = "cancelled"


class WorkflowPhase(str, Enum):
    """工作流阶段"""
    BRAINSTORM = "brainstorm"
    REQUIREMENT = "requirement"
    RETRIEVAL = "retrieval"
    WRITING = "writing"
    REVIEW = "review"


@dataclass
class PhaseResult:
    """阶段执行结果"""
    phase: WorkflowPhase
    success: bool
    duration_seconds: float
    output: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


class WorkflowContext:
    """
    工作流上下文
    在各阶段之间传递数据
    """

    def __init__(self, task_id: str, user_id: str):
        self.task_id = task_id
        self.user_id = user_id
        self.created_at = datetime.now()
        self.updated_at = self.created_at

        # 原始输入
        self.original_description: str = ""
        self.additional_materials: Dict[str, Any] = {}

        # 各阶段输出
        self.brainstorming_output: Dict[str, Any] = {}
        self.requirement_analysis: Dict[str, Any] = {}
        self.retrieval_report: Dict[str, Any] = {}
        self.patent_draft: Dict[str, Any] = {}
        self.review_report: Dict[str, Any] = {}

        # 元数据
        self.iteration_count: int = 0
        self.max_iterations: int = 1
        self.current_phase: WorkflowState = WorkflowState.INITIALIZED
        self.phase_history: List[PhaseResult] = []
        self.metadata: Dict[str, Any] = {}
        self.is_paused: bool = False

        # 迭代修正反馈
        self.latest_revision_suggestions: List[str] = []
        self.latest_review_score: float = 0.0

        # 消息历史
        self.message_history: List[Dict[str, Any]] = []

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """添加消息到历史"""
        now = datetime.now()
        self.message_history.append({
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
            **kwargs,
        })
        self.updated_at = now

    def add_phase_result(self, result: PhaseResult) -> None:
        """添加阶段执行结果"""
        self.phase_history.append(result)
        self.updated_at = datetime.now()

    def get_combined_input(self) -> str:
        """获取整合后的输入（原始描述 + 头脑风暴讨论）"""
        parts = [self.original_description]

        if self.metadata.get("patent_type_preference"):
            parts.append(f"\n\n用户偏好的专利类型: {self.metadata['patent_type_preference']}")

        if self.brainstorming_output and "summary" in self.brainstorming_output:
            parts.append("\n\n补充信息:\n" + self.brainstorming_output["summary"])

        # 添加消息历史中的关键信息
        key_messages = [
            m["content"] for m in self.message_history
            if m.get("role") in ["user", "assistant"] and len(m["content"]) > 50
        ]
        if key_messages:
            parts.append("\n\n讨论摘要:\n" + "\n".join(key_messages[-5:]))

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "current_state": self.current_phase.value,
            "iteration_count": self.iteration_count,
            "phase_count": len(self.phase_history),
            "phases_completed": [p.phase.value for p in self.phase_history],
        }


# ============ 阶段-Profile 映射 ============

_PHASE_TO_PROFILE = {
    WorkflowState.BRAINSTORMING: "patent.brainstorm_partner.v1",
    WorkflowState.REQUIREMENT_ANALYSIS: "patent.requirement_analyst.v1",
    WorkflowState.RETRIEVAL_ANALYSIS: "patent.retrieval_analyst.v1",
    WorkflowState.PATENT_WRITING: "patent.writer.v1",
    WorkflowState.QUALITY_REVIEW: "patent.quality_reviewer.v1",
}

_PHASE_TO_WORKFLOW_PHASE = {
    WorkflowState.BRAINSTORMING: WorkflowPhase.BRAINSTORM,
    WorkflowState.REQUIREMENT_ANALYSIS: WorkflowPhase.REQUIREMENT,
    WorkflowState.RETRIEVAL_ANALYSIS: WorkflowPhase.RETRIEVAL,
    WorkflowState.PATENT_WRITING: WorkflowPhase.WRITING,
    WorkflowState.QUALITY_REVIEW: WorkflowPhase.REVIEW,
}


# ============ 工作流引擎 ============

class PatentWorkflowEngine:
    """
    专利申请工作流引擎
    通过 CEO Agent 动态编排各专业 Agent 完成端到端专利申请流程
    """

    def __init__(self):
        self._logger = get_logger("patent_workflow")
        self._running_workflows: Dict[str, WorkflowContext] = {}

        # 默认完整工作流序列（用于进度计算和兼容）
        self._default_workflow_sequence = [
            WorkflowState.BRAINSTORMING,
            WorkflowState.REQUIREMENT_ANALYSIS,
            WorkflowState.RETRIEVAL_ANALYSIS,
            WorkflowState.PATENT_WRITING,
            WorkflowState.QUALITY_REVIEW,
        ]

    def create_workflow(
        self,
        task_id: str,
        user_id: str,
        description: str,
        patent_type_preference: Optional[str] = None,
        skip_phases: Optional[List[WorkflowState]] = None,
    ) -> WorkflowContext:
        """创建新的工作流"""
        context = WorkflowContext(task_id=task_id, user_id=user_id)
        context.original_description = description
        if patent_type_preference is not None:
            context.metadata = {
                **context.metadata,
                "patent_type_preference": patent_type_preference,
            }

        self._running_workflows[task_id] = context

        self._logger.info(
            "Workflow created",
            task_id=task_id,
            user_id=user_id,
            description_length=len(description),
        )

        return context

    def get_workflow(self, task_id: str) -> Optional[WorkflowContext]:
        """获取工作流上下文"""
        return self._running_workflows.get(task_id)

    def list_workflows(self) -> List[WorkflowContext]:
        """列出所有工作流上下文"""
        return list(self._running_workflows.values())

    async def execute_full_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None]] = None,
    ) -> WorkflowContext:
        """
        执行完整工作流 — CEO Agent 动态调度各专业 Agent

        CEO 通过文本回复表达调度意图，workflow_engine 解析并执行，
        将结果返回给 CEO 继续决策。模拟 tool calling loop。
        """
        self._logger.info("Starting CEO-driven workflow", task_id=context.task_id)

        try:
            service = _get_agent_factory()

            from src.agents.hermes.tools.dispatch_specialist import clear_dispatch_results
            clear_dispatch_results()

            context.current_phase = WorkflowState.REQUIREMENT_ANALYSIS
            await self._publish_progress_event(context, WorkflowState.REQUIREMENT_ANALYSIS, "running")

            # CEO 驱动循环：CEO 决策 → 解析调度意图 → 执行 Agent → 回传结果
            ceo_history = []
            initial_prompt = self._build_ceo_workflow_prompt(context)
            ceo_history.append({"role": "user", "content": initial_prompt})

            max_rounds = 6  # 最多 6 轮（防止死循环）
            phase_agents = {
                "requirement_analyst": ("patent.requirement_analyst.v1", "requirement_analysis", WorkflowState.REQUIREMENT_ANALYSIS, WorkflowPhase.REQUIREMENT),
                "retrieval_analyst": ("patent.retrieval_analyst.v1", "retrieval_report", WorkflowState.RETRIEVAL_ANALYSIS, WorkflowPhase.RETRIEVAL),
                "patent_writer": ("patent.writer.v1", "patent_draft", WorkflowState.PATENT_WRITING, WorkflowPhase.WRITING),
                "quality_reviewer": ("patent.quality_reviewer.v1", "review_report", WorkflowState.QUALITY_REVIEW, WorkflowPhase.REVIEW),
            }

            for round_num in range(max_rounds):
                # CEO 回复（流式，发射thinking事件）
                ceo_text = await self._run_agent_stream(
                    service, "patent.ceo.v1", ceo_history[-1]["content"],
                    context, agent_name="CEO Agent",
                )

                self._logger.info(f"CEO round {round_num+1}: {ceo_text[:100]}...")
                ceo_history.append({"role": "assistant", "content": ceo_text})

                # 解析 CEO 回复中的调度意图
                dispatched = self._extract_dispatch_intent(ceo_text, context)

                if not dispatched:
                    # 检查是否还有未完成阶段
                    done_fields = {
                        "requirement_analysis": bool(context.requirement_analysis),
                        "retrieval_report": bool(context.retrieval_report),
                        "patent_draft": bool(context.patent_draft),
                        "review_report": bool(context.review_report),
                    }
                    pending = [k for k, v in done_fields.items() if not v]
                    
                    if not pending:
                        # 所有阶段都完成了
                        self._logger.info("All phases completed, finishing")
                        break
                    
                    # 还有未完成阶段，强制提示 CEO 继续调度
                    phase_to_agent = {"requirement_analysis": "requirement_analyst", "retrieval_report": "retrieval_analyst", "patent_draft": "patent_writer", "review_report": "quality_reviewer"}
                    next_agent = phase_to_agent[pending[0]]
                    self._logger.info(f"CEO didn't dispatch, forcing next: {next_agent}")
                    
                    force_prompt = f"你还没有调度下一个Agent。未完成阶段: {pending}。请立即调度下一个Agent：\n\ndispatch_specialist(agent_id=\"{next_agent}\", task=\"请执行你的专业工作\")"
                    ceo_history.append({"role": "user", "content": force_prompt})
                    continue

                # 执行 CEO 指示的 Agent 调度
                for agent_id, task_desc in dispatched:
                    if agent_id not in phase_agents:
                        continue

                    profile_id, context_field, phase_state, phase_enum = phase_agents[agent_id]

                    # Agent名称映射（用于前端展示）
                    agent_display_names = {
                        "requirement_analyst": "需求分析 Agent",
                        "retrieval_analyst": "检索分析 Agent",
                        "patent_writer": "专利撰写 Agent",
                        "quality_reviewer": "质量审查 Agent",
                    }
                    agent_display_name = agent_display_names.get(agent_id, agent_id)

                    # 发射 CEO 调度事件
                    await publish_event(AgentDispatchEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        from_agent="CEO Agent",
                        to_agent=agent_display_name,
                        task_description=task_desc[:300],
                    ))

                    context.current_phase = phase_state
                    await self._publish_progress_event(context, phase_state, "running")

                    # 流式调用专业 Agent（发射thinking/tool_call事件）
                    self._logger.info(f"CEO dispatched: {agent_id} → {profile_id}")
                    agent_text = await self._run_agent_stream(
                        service, profile_id, task_desc,
                        context, agent_name=agent_display_name,
                    )

                    # 尝试解析 Agent 输出中的 JSON 结构化数据
                    parsed_output = self._try_parse_json(agent_text)
                    
                    # 如果解析出结构化数据（非 raw_output 包装），直接用作 context 字段
                    # 这样前端能直接访问 outputs.patent_draft.claims 等嵌套字段
                    if "raw_output" not in parsed_output:
                        context_data = parsed_output
                    else:
                        # 降级为文本存储
                        context_data = {
                            "agent": agent_id,
                            "output": agent_text,
                            "summary": agent_text[:500],
                        }

                    # 发射 Agent 输出完成事件
                    await publish_event(AgentContentEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_display_name,
                        content=agent_text[:500],
                        phase=phase_state.value,
                    ))

                    # 存储到 context
                    setattr(context, context_field, context_data)

                    context.add_phase_result(PhaseResult(
                        phase=phase_enum,
                        success=True,
                        duration_seconds=0,
                        output=getattr(context, context_field),
                    ))
                    await self._publish_progress_event(context, phase_state, "completed")

                    if phase_callback:
                        if asyncio.iscoroutinefunction(phase_callback):
                            await phase_callback(phase_state, context.phase_history[-1])
                        else:
                            phase_callback(phase_state, context.phase_history[-1])

                # 将执行结果回传给 CEO 进行下一轮决策
                results_summary = "\n".join([
                    f"[{aid}] 已完成，输出内容:\n{getattr(context, phase_agents[aid][1], {}).get('output', '')[:800]}"
                    for aid, _ in dispatched if aid in phase_agents
                ])

                # 确定已完成和未完成的阶段
                done_phases = [k for k, v in {
                    "requirement_analysis": context.requirement_analysis,
                    "retrieval_report": context.retrieval_report,
                    "patent_draft": context.patent_draft,
                    "review_report": context.review_report,
                }.items() if v]
                pending_phases = [k for k in ["requirement_analysis", "retrieval_report", "patent_draft", "review_report"] if k not in done_phases]
                phase_to_agent = {"requirement_analysis": "requirement_analyst", "retrieval_report": "retrieval_analyst", "patent_draft": "patent_writer", "review_report": "quality_reviewer"}

                if pending_phases:
                    next_hint = f"\n\n下一步应调度: dispatch_specialist(agent_id=\"{phase_to_agent[pending_phases[0]]}\", task=\"...\")"
                else:
                    next_hint = "\n\n所有阶段已完成，请说'流程完成'。"

                ceo_history.append({"role": "user", "content": f"Agent 执行结果：\n{results_summary}\n\n已完成阶段: {done_phases}\n未完成阶段: {pending_phases}{next_hint}"})

            # 标记完成
            context.current_phase = WorkflowState.COMPLETED
            await self._publish_progress_event(context, WorkflowState.COMPLETED, "completed")

            context.brainstorming_output = {
                "summary": ceo_text[:500] if ceo_text else "流程已完成",
                "ceo_rounds": round_num + 1,
            }

            self._logger.info("CEO-driven workflow completed", task_id=context.task_id, rounds=round_num+1)
            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            raise
        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error("Workflow failed", task_id=context.task_id, error=str(e), exc_info=True)
            raise

    def _extract_dispatch_intent(self, ceo_text: str, context: "WorkflowContext" = None) -> list:
        """从 CEO 回复文本中解析调度意图"""
        import re

        results = []

        # Agent 名称映射
        name_to_id = {
            "需求分析": "requirement_analyst",
            "requirement_analyst": "requirement_analyst",
            "检索分析": "retrieval_analyst",
            "retrieval_analyst": "retrieval_analyst",
            "专利撰写": "patent_writer",
            "patent_writer": "patent_writer",
            "撰写师": "patent_writer",
            "质量审查": "quality_reviewer",
            "quality_reviewer": "quality_reviewer",
            "审查师": "quality_reviewer",
        }

        # 模式1: dispatch_specialist(agent_id="xxx", task="xxx")
        pattern1 = r'dispatch_specialist\s*\(\s*agent_id\s*=\s*["\'](\w+)["\'](?:\s*,\s*task\s*=\s*["\'](.+?)["\'])?\s*\)'
        for m in re.finditer(pattern1, ceo_text, re.IGNORECASE | re.DOTALL):
            agent_id = m.group(1)
            task = m.group(2) or self._build_default_task_for_agent(agent_id, context)
            results.append((agent_id, task))

        if results:
            return results

        # 模式2: "调度/派发给 XXX" 中文表达
        for name, agent_id in name_to_id.items():
            patterns = [
                f"(?:调度|派发|交给|启动|调用).*?{name}",
                f"{name}.*?(?:Agent|agent|专家|师)",
            ]
            for p in patterns:
                if re.search(p, ceo_text):
                    task = self._build_default_task_for_agent(agent_id, context)
                    if agent_id not in [r[0] for r in results]:
                        results.append((agent_id, task))
                    break

        # 模式3: 检测"流程完成"/"全部完成"信号
        if re.search(r'流程完成|全部完成|交付用户|专利文件已完成', ceo_text):
            return []

        return results

    def _build_default_task_for_agent(self, agent_id: str, context: "WorkflowContext" = None) -> str:
        """为调度生成包含完整技术描述的任务 prompt"""
        tech_desc = context.original_description if context else "（未提供技术描述）"
        req_summary = json.dumps(context.requirement_analysis, ensure_ascii=False)[:800] if context and context.requirement_analysis else ""
        ret_summary = json.dumps(context.retrieval_report, ensure_ascii=False)[:800] if context and context.retrieval_report else ""
        draft_summary = json.dumps(context.patent_draft, ensure_ascii=False)[:800] if context and context.patent_draft else ""

        tasks = {
            "requirement_analyst": f"对以下技术方案进行结构化需求分析，提取创新点、确定IPC分类、输出结构化需求文档。\n\n技术方案：\n{tech_desc}",
            "retrieval_analyst": f"基于以下需求分析结果进行先有技术检索和专利性评估（新颖性、创造性、实用性）。\n\n需求分析结果：\n{req_summary}\n\n原始技术描述：\n{tech_desc[:500]}",
            "patent_writer": f"基于以下需求分析和检索结果，撰写完整的专利申请文件（权利要求书+说明书+摘要）。\n\n需求分析：\n{req_summary}\n\n检索结果：\n{ret_summary}",
            "quality_reviewer": f"对以下专利申请文件进行形式审查和实质审查。\n\n专利文件：\n{draft_summary}",
        }
        return tasks.get(agent_id, f"执行专业分析任务。\n\n技术描述：\n{tech_desc}")

    async def resume_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None]] = None,
        force_start_from: Optional[WorkflowState] = None,
    ) -> WorkflowContext:
        """
        恢复工作流 — 重新启动 CEO 编排

        由于 CEO 是动态编排，恢复就是重新发起 CEO 对话，
        并在 prompt 中注入已有阶段产出作为上下文。
        """
        self._logger.info(
            "Resuming workflow via CEO",
            task_id=context.task_id,
            force_start_from=force_start_from.value if force_start_from else None,
        )

        if force_start_from:
            context.current_phase = WorkflowState.ITERATION
            context.iteration_count += 1

        try:
            service = _get_agent_factory()

            # 构建带已有成果的恢复 prompt
            prompt = self._build_ceo_resume_prompt(context, force_start_from)

            result_text = await service.run_conversation("patent.ceo.v1", prompt)
            if isinstance(result_text, dict):
                result_text = result_text.get("final_response", "") or result_text.get("content", "") or json.dumps(result_text, ensure_ascii=False)
            else:
                result_text = str(result_text) if result_text else ""

            self._parse_ceo_output(context, result_text)

            context.current_phase = WorkflowState.COMPLETED
            await self._publish_progress_event(context, WorkflowState.COMPLETED, "completed")

            if phase_callback:
                result = PhaseResult(
                    phase=WorkflowPhase.REVIEW,
                    success=True,
                    duration_seconds=(datetime.now() - context.updated_at).total_seconds(),
                    output={"ceo_summary": result_text[:1000]},
                )
                if asyncio.iscoroutinefunction(phase_callback):
                    await phase_callback(WorkflowState.COMPLETED, result)
                else:
                    phase_callback(WorkflowState.COMPLETED, result)

            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            raise

        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error("Workflow resume failed", error=str(e), exc_info=True)
            raise

    async def execute_phase(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
    ) -> PhaseResult:
        """执行单个阶段 — 直接调用对应专业 Agent"""
        start_time = datetime.now()
        profile_id = _PHASE_TO_PROFILE.get(phase)
        workflow_phase = _PHASE_TO_WORKFLOW_PHASE.get(phase, WorkflowPhase.BRAINSTORM)

        if not profile_id:
            return PhaseResult(
                phase=workflow_phase,
                success=False,
                duration_seconds=0,
                issues=[f"No profile mapped for phase: {phase}"],
            )

        try:
            service = _get_agent_factory()
            prompt = self._build_phase_prompt(context, phase)

            result_text = await service.run_conversation(profile_id, prompt)
            if isinstance(result_text, dict):
                result_text = result_text.get("final_response", "") or result_text.get("content", "") or json.dumps(result_text, ensure_ascii=False)
            else:
                result_text = str(result_text) if result_text else ""

            duration = (datetime.now() - start_time).total_seconds()

            # 尝试解析 JSON 输出
            output = self._try_parse_json(result_text)

            return PhaseResult(
                phase=workflow_phase,
                success=True,
                duration_seconds=duration,
                output=output,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self._logger.error(f"Phase {phase.value} failed: {e}", exc_info=True)
            return PhaseResult(
                phase=workflow_phase,
                success=False,
                duration_seconds=duration,
                issues=[str(e)],
            )

    async def add_chat_message(
        self,
        task_id: str,
        role: str,
        content: str,
    ) -> Dict[str, Any]:
        """添加聊天消息到工作流（用于头脑风暴阶段）"""
        context = self.get_workflow(task_id)
        if not context:
            raise ValueError(f"Workflow not found: {task_id}")

        context.add_message(role, content)

        # 如果是用户消息，通过 CEO 生成回复
        if role == "user" and context.current_phase in [
            WorkflowState.INITIALIZED,
            WorkflowState.BRAINSTORMING,
        ]:
            service = _get_agent_factory()

            # 构建对话历史
            history_text = "\n".join([
                f"{m['role'].upper()}: {m['content']}"
                for m in context.message_history[-10:]
            ])

            prompt = f"""
基于以下对话历史，继续与用户讨论专利申请方案：

{history_text}

请友好地回应用户，提供专业的建议，必要时可以提问以获取更多信息。
"""

            response = await service.run_conversation("patent.brainstorm_partner.v1", prompt)
            if isinstance(response, dict):
                response_text = response.get("final_response", "") or response.get("content", "") or str(response)
            else:
                response_text = str(response) if response else ""
            context.add_message("assistant", response_text)

            return {
                "role": "assistant",
                "content": response_text,
                "phase": context.current_phase.value,
            }

        return {"status": "added"}

    def cancel_workflow(self, task_id: str) -> bool:
        """取消工作流"""
        context = self._running_workflows.pop(task_id, None)
        if context:
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=task_id)
            return True
        return False

    # ============ 内部辅助方法 ============

    def _build_ceo_workflow_prompt(self, context: WorkflowContext) -> str:
        """构建 CEO 工作流 prompt — 引导 CEO 表达调度意图"""
        patent_type = context.metadata.get("patent_type_preference", "未指定")
        return f"""执行完整的专利申请流程。你是调度者，通过指示我调用对应的专业Agent来完成各阶段工作。

【你的指令格式】
当你需要调度某个Agent时，请明确写出：
  dispatch_specialist(agent_id="xxx", task="具体任务描述")

可用的 agent_id：
- requirement_analyst：需求分析（提取创新点、IPC分类）
- retrieval_analyst：检索分析（先有技术检索、专利性评估）
- patent_writer：专利撰写（权利要求书+说明书+摘要）
- quality_reviewer：质量审查（形式+实质审查）

【技术描述】
{context.original_description}

【用户偏好专利类型】{patent_type}

请评估技术方案后，调度第一个Agent。输出格式示例：
dispatch_specialist(agent_id="requirement_analyst", task="对以下技术方案进行结构化需求分析...")"""

    def _build_ceo_resume_prompt(
        self, context: WorkflowContext, force_start_from: Optional[WorkflowState]
    ) -> str:
        """构建 CEO 恢复工作流 prompt"""
        existing_outputs = []
        if context.requirement_analysis:
            existing_outputs.append(f"需求分析已完成: {json.dumps(context.requirement_analysis, ensure_ascii=False)[:500]}")
        if context.retrieval_report:
            existing_outputs.append(f"检索报告已完成: {json.dumps(context.retrieval_report, ensure_ascii=False)[:500]}")
        if context.patent_draft:
            existing_outputs.append(f"专利草稿已完成: {json.dumps(context.patent_draft, ensure_ascii=False)[:500]}")
        if context.review_report:
            existing_outputs.append(f"审查报告已完成: {json.dumps(context.review_report, ensure_ascii=False)[:500]}")

        existing_text = "\n".join(existing_outputs) if existing_outputs else "无"

        start_hint = ""
        if force_start_from:
            start_hint = f"\n请从【{force_start_from.value}】阶段重新开始（这是第{context.iteration_count}轮迭代修正）。"

        return f"""继续执行专利申请流程。

【技术描述】
{context.original_description}

【已有成果】
{existing_text}

【修正建议】
{json.dumps(context.latest_revision_suggestions, ensure_ascii=False) if context.latest_revision_suggestions else "无"}
{start_hint}
请评估已有成果，根据修正建议使用 dispatch_specialist 继续推进流程直到完成。"""

    def _build_phase_prompt(self, context: WorkflowContext, phase: WorkflowState) -> str:
        """为单个阶段构建 prompt"""
        base = context.get_combined_input()

        if phase == WorkflowState.BRAINSTORMING:
            return f"请帮我梳理这项技术发明的专利申请思路：\n\n{base}"

        elif phase == WorkflowState.REQUIREMENT_ANALYSIS:
            return f"对以下技术方案进行结构化需求分析，提取创新点和技术特征：\n\n{base}"

        elif phase == WorkflowState.RETRIEVAL_ANALYSIS:
            req = json.dumps(context.requirement_analysis, ensure_ascii=False)[:1000]
            return f"基于以下需求分析结果进行先有技术检索和专利性评估：\n\n{req}\n\n原始描述：{context.original_description[:500]}"

        elif phase == WorkflowState.PATENT_WRITING:
            req = json.dumps(context.requirement_analysis, ensure_ascii=False)[:500]
            ret = json.dumps(context.retrieval_report, ensure_ascii=False)[:500]
            return f"基于需求分析和检索结果撰写专利申请文件：\n\n需求：{req}\n\n检索：{ret}"

        elif phase == WorkflowState.QUALITY_REVIEW:
            draft = json.dumps(context.patent_draft, ensure_ascii=False)[:1000]
            return f"对以下专利申请文件进行质量审查：\n\n{draft}"

        return base

    def _parse_ceo_output(self, context: WorkflowContext, result_text: str) -> None:
        """从 dispatch_specialist 缓存中读取各专业 Agent 的实际输出填入 context

        每个阶段的输出来自对应的专业 Agent（而非 CEO 的总结），
        确保数据的专业性和可追溯性。
        """
        from src.agents.hermes.tools.dispatch_specialist import (
            get_dispatch_results,
            get_latest_result_by_phase,
        )

        # 保存 CEO 的总结性回复
        context.brainstorming_output = {
            "summary": result_text[:500] if result_text else "",
            "ceo_response": result_text,
        }

        # 从各专业 Agent 的实际输出填充 context
        req_result = get_latest_result_by_phase("requirement_analysis")
        if req_result and req_result.get("status") == "completed":
            context.requirement_analysis = {
                "agent": req_result.get("agent", ""),
                "output": req_result.get("result", ""),
                "summary": req_result.get("result", "")[:500],
                "task": req_result.get("task", ""),
            }

        ret_result = get_latest_result_by_phase("retrieval_report")
        if ret_result and ret_result.get("status") == "completed":
            context.retrieval_report = {
                "agent": ret_result.get("agent", ""),
                "output": ret_result.get("result", ""),
                "summary": ret_result.get("result", "")[:500],
                "task": ret_result.get("task", ""),
            }

        draft_result = get_latest_result_by_phase("patent_draft")
        if draft_result and draft_result.get("status") == "completed":
            context.patent_draft = {
                "agent": draft_result.get("agent", ""),
                "output": draft_result.get("result", ""),
                "summary": draft_result.get("result", "")[:500],
                "task": draft_result.get("task", ""),
            }

        review_result = get_latest_result_by_phase("review_report")
        if review_result and review_result.get("status") == "completed":
            context.review_report = {
                "agent": review_result.get("agent", ""),
                "output": review_result.get("result", ""),
                "summary": review_result.get("result", "")[:500],
                "task": review_result.get("task", ""),
            }

    async def _call_agent_with_continuation(self, service, profile_id: str, task: str, max_rounds: int = 3) -> str:
        """调用 Agent 并让其自检输出完整性，不完整则补充直到满意

        流程：
        1. Agent 执行任务
        2. 检测输出是否完整（JSON 闭合 + 内容完整性）
        3. 如果不完整，让 Agent 自检并补充
        4. Agent 确认完整后才返回
        """
        # 第一次调用
        raw = await service.run_conversation(profile_id, task)
        if isinstance(raw, dict):
            text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
        else:
            text = str(raw) if raw else ""

        full_text = text

        # 自检循环
        for i in range(max_rounds):
            # 检测是否被截断
            is_truncated = self._is_output_truncated(full_text)

            if not is_truncated:
                break

            self._logger.info(f"Agent output incomplete (round {i+1}), asking to continue")

            # 让 Agent 自检并补充（不同于简单的"继续"，而是要求 Agent 确认完整性）
            if i == 0:
                continuation_prompt = (
                    "你的输出被截断了，没有完成。请从截断处继续输出剩余内容。"
                    "注意：\n"
                    "1. 不要重复已输出的内容，直接从上次停止的地方继续\n"
                    "2. 确保 JSON 格式完整闭合\n"
                    "3. 确保所有必要字段都有实质内容\n"
                    "4. 输出完成后确保以正确的 } 和 ``` 结尾"
                )
            else:
                continuation_prompt = (
                    "继续输出，确保完整闭合所有 JSON 括号。直接输出剩余内容。"
                )

            raw = await service.run_conversation(profile_id, continuation_prompt)
            if isinstance(raw, dict):
                cont_text = raw.get("final_response", "") or raw.get("content", "") or ""
            else:
                cont_text = str(raw) if raw else ""

            if not cont_text or len(cont_text) < 10:
                break

            full_text += "\n" + cont_text

        # 最终完整性验证
        if self._is_output_truncated(full_text):
            self._logger.warning(f"Agent output still incomplete after {max_rounds} rounds, using repair")
            # 尝试修复
            repaired = self._repair_truncated_json(self._extract_json_content(full_text))
            if repaired:
                full_text = repaired

        return full_text

    def _is_output_truncated(self, text: str) -> bool:
        """检测输出是否被截断"""
        if not text:
            return False

        # 检测 JSON 结构完整性
        triple = chr(96) * 3
        has_json_start = (triple + "json") in text or text.strip().startswith("{")

        if not has_json_start:
            return False  # 非 JSON 输出，不检测

        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")

        return open_braces > 0 or open_brackets > 0

    def _extract_json_content(self, text: str) -> str:
        """从文本中提取 JSON 内容（去掉 markdown 包装）"""
        triple = chr(96) * 3
        start_marker = triple + "json"
        start_idx = text.find(start_marker)
        if start_idx >= 0:
            content = text[start_idx + len(start_marker):]
            end_idx = content.find(triple)
            if end_idx >= 0:
                return content[:end_idx].strip()
            return content.strip()
        return text

    def _try_parse_json(self, text: str) -> Dict[str, Any]:
        """尝试从文本中解析 JSON，支持处理截断的 JSON"""
        import re

        if not text:
            return {"raw_output": ""}

        # 尝试直接解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从 markdown code block 中提取
        triple = chr(96) * 3  # ```
        start_marker = triple + "json"
        start_idx = text.find(start_marker)

        if start_idx >= 0:
            # 找闭合的 ```
            content_start = start_idx + len(start_marker)
            end_idx = text.find(triple, content_start)

            if end_idx > content_start:
                json_str = text[content_start:end_idx].strip()
            else:
                # 没有闭合 — JSON 被截断，取剩余全部
                json_str = text[content_start:].strip()

            # 尝试直接解析
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # 尝试修复截断的 JSON（补充缺失的闭合括号）
            repaired = self._repair_truncated_json(json_str)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        # 尝试找文本中第一个 { 到最后一个 } 的范围
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        # 返回原始文本
        return {"raw_output": text}

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """尝试修复被截断的 JSON（补充缺失的闭合括号和引号）"""
        if not json_str:
            return None

        # 统计未闭合的括号
        open_braces = json_str.count("{") - json_str.count("}")
        open_brackets = json_str.count("[") - json_str.count("]")

        if open_braces <= 0 and open_brackets <= 0:
            return None  # 不需要修复

        # 截断到最后一个完整的 key-value 对（最后一个逗号或冒号后的值）
        # 去掉最后一个不完整的值
        repaired = json_str.rstrip()

        # 去掉尾部不完整的内容（截断可能停在字符串中间）
        # 找到最后一个完整的行
        lines = repaired.split("\n")
        while lines:
            last_line = lines[-1].strip()
            # 如果最后一行看起来不完整（没有闭合引号、逗号等），去掉它
            if last_line and not last_line.endswith((",", "}", "]", '"', "true", "false", "null")) and not last_line[-1].isdigit():
                lines.pop()
            else:
                break

        repaired = "\n".join(lines)

        # 移除尾部悬挂的逗号
        repaired = repaired.rstrip().rstrip(",")

        # 补充闭合括号
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        repaired += "]" * open_brackets + "}" * open_braces

        return repaired

    async def _run_agent_stream(
        self,
        service,
        profile_id: str,
        user_input: str,
        context: WorkflowContext,
        agent_name: str,
    ) -> str:
        """
        流式调用 Agent 并实时发射事件到前端。
        返回 agent 的最终文本输出。
        """
        content_chunks: List[str] = []
        final_text = ""

        try:
            async for event in service.run_conversation_stream(
                profile_id=profile_id,
                user_input=user_input,
            ):
                event_type = event.get("type", "")
                event_data = event.get("data", {})

                if event_type == "thinking":
                    await publish_event(AgentThinkingEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_name,
                        thought=event_data.get("message", ""),
                        step=event_data.get("iteration", 0),
                    ))

                elif event_type == "tool_call_start":
                    await publish_event(AgentToolCallStartEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_name,
                        tool_name=event_data.get("name", ""),
                        parameters=event_data.get("parameters", {}),
                    ))

                elif event_type == "tool_call_end":
                    await publish_event(AgentToolCallEndEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_name,
                        tool_name=event_data.get("name", ""),
                        parameters=event_data.get("parameters", {}),
                        result=str(event_data.get("result", ""))[:500],
                        success=event_data.get("success", True),
                    ))

                elif event_type == "content_delta":
                    content_chunks.append(event_data.get("delta", ""))

                elif event_type == "content":
                    final_text = event_data.get("content", "")

                elif event_type == "done":
                    msg = event_data.get("message", {})
                    if isinstance(msg, dict) and msg.get("content"):
                        final_text = msg["content"]

                elif event_type == "error":
                    self._logger.error(
                        "Agent stream error",
                        agent=agent_name,
                        error=event_data.get("error", ""),
                    )

        except Exception as e:
            self._logger.error(
                "Agent stream failed, falling back to sync",
                agent=agent_name,
                error=str(e),
            )
            # Fallback: 同步调用
            raw = await service.run_conversation(profile_id, user_input)
            if isinstance(raw, dict):
                final_text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
            else:
                final_text = str(raw) if raw else ""

        # 如果有 stream delta chunks 则拼接
        if content_chunks and not final_text:
            final_text = "".join(content_chunks)

        return final_text

    async def _publish_progress_event(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
        status: str,
        result: Optional[PhaseResult] = None,
    ) -> None:
        """发布进度事件"""
        try:
            from src.core.events import EventType, TaskProgressUpdatedEvent

            event = TaskProgressUpdatedEvent(
                event_type=EventType.WORKFLOW_PROGRESS_UPDATED,
                task_id=context.task_id,
                user_id=context.user_id,
                state=phase.value,
                progress=self._calculate_progress(context, phase, status),
                message=f"Phase {phase.value} {status}",
            )

            await publish_event(event)

        except Exception as e:
            self._logger.warning("Failed to publish progress event", error=str(e))

    def _calculate_progress(self, context: WorkflowContext, current_phase: WorkflowState, status: str) -> int:
        """计算总体进度百分比"""
        if current_phase == WorkflowState.COMPLETED:
            return 100
        if current_phase not in self._default_workflow_sequence:
            return 0
        if status == "completed":
            completed_index = self._default_workflow_sequence.index(current_phase) + 1
            return int((completed_index / len(self._default_workflow_sequence)) * 100)
        else:
            current_index = self._default_workflow_sequence.index(current_phase)
            return int((current_index / len(self._default_workflow_sequence)) * 100)


# 全局工作流引擎实例
_global_workflow_engine: Optional[PatentWorkflowEngine] = None


def get_workflow_engine() -> PatentWorkflowEngine:
    """获取全局工作流引擎实例"""
    global _global_workflow_engine
    if _global_workflow_engine is None:
        _global_workflow_engine = PatentWorkflowEngine()
    return _global_workflow_engine
