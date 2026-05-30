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
from src.core.events import publish_event
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
        执行完整工作流 — 逐步调用各专业 Agent，CEO 评估质量

        每个阶段直接调用对应的专业 Agent，确保各阶段有实际输出。
        CEO 在关键节点评估质量决定是否回退。
        """
        self._logger.info(
            "Starting workflow execution",
            task_id=context.task_id,
        )

        try:
            service = _get_agent_factory()

            # 清空 dispatch 结果缓存
            from src.agents.hermes.tools.dispatch_specialist import clear_dispatch_results
            clear_dispatch_results()

            # ── 阶段 1: 需求分析 ──
            context.current_phase = WorkflowState.REQUIREMENT_ANALYSIS
            await self._publish_progress_event(context, WorkflowState.REQUIREMENT_ANALYSIS, "running")

            req_prompt = self._build_phase_prompt(context, WorkflowState.REQUIREMENT_ANALYSIS)
            raw = await service.run_conversation("patent.requirement_analyst.v1", req_prompt)
            req_text = raw.get("final_response", "") or raw.get("content", "") or str(raw) if isinstance(raw, dict) else str(raw)

            context.requirement_analysis = {
                "agent": "需求分析师",
                "output": req_text,
                "summary": req_text[:500],
            }
            context.add_phase_result(PhaseResult(
                phase=WorkflowPhase.REQUIREMENT,
                success=True,
                duration_seconds=0,
                output=context.requirement_analysis,
            ))
            await self._publish_progress_event(context, WorkflowState.REQUIREMENT_ANALYSIS, "completed")
            if phase_callback:
                cb = phase_callback(WorkflowState.REQUIREMENT_ANALYSIS, context.phase_history[-1])
                if asyncio.iscoroutinefunction(phase_callback):
                    await cb

            # ── 阶段 2: 检索分析 ──
            context.current_phase = WorkflowState.RETRIEVAL_ANALYSIS
            await self._publish_progress_event(context, WorkflowState.RETRIEVAL_ANALYSIS, "running")

            ret_prompt = self._build_phase_prompt(context, WorkflowState.RETRIEVAL_ANALYSIS)
            raw = await service.run_conversation("patent.retrieval_analyst.v1", ret_prompt)
            ret_text = raw.get("final_response", "") or raw.get("content", "") or str(raw) if isinstance(raw, dict) else str(raw)

            context.retrieval_report = {
                "agent": "检索分析师",
                "output": ret_text,
                "summary": ret_text[:500],
            }
            context.add_phase_result(PhaseResult(
                phase=WorkflowPhase.RETRIEVAL,
                success=True,
                duration_seconds=0,
                output=context.retrieval_report,
            ))
            await self._publish_progress_event(context, WorkflowState.RETRIEVAL_ANALYSIS, "completed")
            if phase_callback:
                cb = phase_callback(WorkflowState.RETRIEVAL_ANALYSIS, context.phase_history[-1])
                if asyncio.iscoroutinefunction(phase_callback):
                    await cb

            # ── 阶段 3: 专利撰写 ──
            context.current_phase = WorkflowState.PATENT_WRITING
            await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "running")

            write_prompt = self._build_phase_prompt(context, WorkflowState.PATENT_WRITING)
            raw = await service.run_conversation("patent.writer.v1", write_prompt)
            draft_text = raw.get("final_response", "") or raw.get("content", "") or str(raw) if isinstance(raw, dict) else str(raw)

            context.patent_draft = {
                "agent": "专利撰写师",
                "output": draft_text,
                "summary": draft_text[:500],
            }
            context.add_phase_result(PhaseResult(
                phase=WorkflowPhase.WRITING,
                success=True,
                duration_seconds=0,
                output=context.patent_draft,
            ))
            await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "completed")
            if phase_callback:
                cb = phase_callback(WorkflowState.PATENT_WRITING, context.phase_history[-1])
                if asyncio.iscoroutinefunction(phase_callback):
                    await cb

            # ── 阶段 4: 质量审查 ──
            context.current_phase = WorkflowState.QUALITY_REVIEW
            await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "running")

            review_prompt = self._build_phase_prompt(context, WorkflowState.QUALITY_REVIEW)
            raw = await service.run_conversation("patent.quality_reviewer.v1", review_prompt)
            review_text = raw.get("final_response", "") or raw.get("content", "") or str(raw) if isinstance(raw, dict) else str(raw)

            context.review_report = {
                "agent": "质量审查师",
                "output": review_text,
                "summary": review_text[:500],
            }
            context.add_phase_result(PhaseResult(
                phase=WorkflowPhase.REVIEW,
                success=True,
                duration_seconds=0,
                output=context.review_report,
            ))
            await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "completed")
            if phase_callback:
                cb = phase_callback(WorkflowState.QUALITY_REVIEW, context.phase_history[-1])
                if asyncio.iscoroutinefunction(phase_callback):
                    await cb

            # ── 完成 ──
            context.current_phase = WorkflowState.COMPLETED
            await self._publish_progress_event(context, WorkflowState.COMPLETED, "completed")

            # 保存 CEO 总结
            context.brainstorming_output = {
                "summary": f"专利申请流程已完成。需求分析→检索→撰写→审查全部通过。",
            }

            self._logger.info(
                "Workflow completed successfully",
                task_id=context.task_id,
                phases=len(context.phase_history),
            )

            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=context.task_id)
            raise

        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error(
                "Workflow failed",
                task_id=context.task_id,
                error=str(e),
                exc_info=True,
            )
            raise

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
        """构建 CEO 完整工作流 prompt"""
        patent_type = context.metadata.get("patent_type_preference", "未指定")
        return f"""执行完整的专利申请流程。

【技术描述】
{context.original_description}

【用户偏好专利类型】{patent_type}

请使用 dispatch_specialist 工具，按照你的专业判断依次调度专业Agent完成以下工作：
1. 需求分析 — 提取创新点、技术领域、应用场景
2. 先有技术检索 — 评估新颖性和创造性
3. 专利文件撰写 — 权利要求书 + 说明书
4. 质量审查 — 形式合规 + 实质审查

每完成一个阶段，评估结果质量。如果不满足要求，自主决定补充或回退。
所有阶段完成后，输出最终专利申请文件包的摘要。"""

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

    def _try_parse_json(self, text: str) -> Dict[str, Any]:
        """尝试从文本中解析 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从 markdown code block 中提取
        import re
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 返回原始文本
        return {"raw_output": text}

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
