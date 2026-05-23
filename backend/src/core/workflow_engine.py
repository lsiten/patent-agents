"""
专利申请工作流编排引擎
协调 CEO Agent 与各专业 Agent 完成端到端专利申请流程
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
    """Lazy import to break circular dependency:
    agents -> hermes -> core.config -> core.__init__ -> container -> services -> workflow -> agents
    """
    from src.agents import get_agent_factory as _f

    return _f()

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
        self.max_iterations: int = 3
        self.current_phase: WorkflowState = WorkflowState.INITIALIZED
        self.phase_history: List[PhaseResult] = []
        self.metadata: Dict[str, Any] = {}

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


class WorkflowPhaseExecutor:
    """阶段执行器抽象基类"""

    def __init__(self, context: WorkflowContext):
        self.context = context
        self._logger = get_logger(f"phase_{self.__class__.__name__}")

    async def execute(self) -> PhaseResult:
        """执行阶段"""
        raise NotImplementedError

    def get_agent_profile_id(self) -> str:
        """获取该阶段对应的 Agent Profile ID"""
        raise NotImplementedError


class BrainstormingPhaseExecutor(WorkflowPhaseExecutor):
    """头脑风暴阶段执行器"""

    def get_agent_profile_id(self) -> str:
        return "patent.brainstorm_partner.v1"

    async def execute(self) -> PhaseResult:
        start_time = datetime.now()

        self._logger.info("Starting brainstorming phase", task_id=self.context.task_id)

        try:
            factory = _get_agent_factory()
            agent = factory.create_agent(self.get_agent_profile_id())

            # 构建提示词
            prompt = f"""
请帮我梳理这项技术发明的专利申请思路。

技术描述：
{self.context.original_description}

请从以下几个方面进行分析和提问，帮助我完善专利申请方案：
1. 技术领域的精确定位
2. 核心技术问题的识别
3. 创新点的挖掘方向
4. 可能的保护范围建议
5. 任何需要我补充说明的技术细节

请以友好的对话方式与我讨论。
"""

            # 执行 Agent
            result = await agent.run(prompt)

            # 保存输出
            self.context.brainstorming_output = {
                "initial_analysis": str(result),
                "summary": str(result)[:500] + "..." if len(str(result)) > 500 else str(result),
            }

            duration = (datetime.now() - start_time).total_seconds()

            return PhaseResult(
                phase=WorkflowPhase.BRAINSTORM,
                success=True,
                duration_seconds=duration,
                output=self.context.brainstorming_output,
            )

        except Exception as e:
            self._logger.error("Brainstorming phase failed", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.BRAINSTORM,
                success=False,
                duration_seconds=duration,
                issues=[f"头脑风暴阶段失败: {str(e)}"],
            )


class RequirementAnalysisPhaseExecutor(WorkflowPhaseExecutor):
    """需求分析阶段执行器"""

    def get_agent_profile_id(self) -> str:
        return "patent.requirement_analyst.v1"

    async def execute(self) -> PhaseResult:
        start_time = datetime.now()

        self._logger.info("Starting requirement analysis phase", task_id=self.context.task_id)

        try:
            factory = _get_agent_factory()
            agent = factory.create_agent(self.get_agent_profile_id())

            combined_input = self.context.get_combined_input()

            # 定义输出 Schema
            output_schema = {
                "type": "object",
                "properties": {
                    "tech_field": {"type": "string", "description": "技术领域"},
                    "core_principle": {"type": "string", "description": "核心原理"},
                    "technical_problem": {"type": "string", "description": "解决的技术问题"},
                    "beneficial_effects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "有益效果列表",
                    },
                    "key_innovative_features": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "technical_significance": {"type": "string"},
                            },
                        },
                    },
                    "application_scenarios": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "patent_type_recommendation": {
                        "type": "object",
                        "properties": {
                            "suggested_type": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                    },
                    "information_gaps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["tech_field", "core_principle", "key_innovative_features"],
            }

            # 使用结构化输出
            from src.core.llm_client import get_llm_service, LLMMessage

            llm_service = get_llm_service()
            messages = [
                LLMMessage(role="system", content=agent._build_system_prompt()),
                LLMMessage(role="user", content=combined_input),
            ]

            result = await llm_service.structured_output(messages, output_schema)

            self.context.requirement_analysis = result

            # 检查是否有严重的信息缺口
            issues = []
            if len(result.get("information_gaps", [])) > 3:
                issues.append(f"发现 {len(result['information_gaps'])} 个信息缺口，建议补充后继续")

            duration = (datetime.now() - start_time).total_seconds()

            return PhaseResult(
                phase=WorkflowPhase.REQUIREMENT,
                success=True,
                duration_seconds=duration,
                output=result,
                issues=issues,
            )

        except LLMError as e:
            self._logger.error("LLM call failed during requirement analysis", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.REQUIREMENT,
                success=False,
                duration_seconds=duration,
                issues=[f"需求分析阶段LLM调用失败: {str(e)}"],
            )

        except Exception as e:
            self._logger.error("Requirement analysis phase failed", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.REQUIREMENT,
                success=False,
                duration_seconds=duration,
                issues=[f"需求分析阶段失败: {str(e)}"],
            )


class RetrievalAnalysisPhaseExecutor(WorkflowPhaseExecutor):
    """检索分析阶段执行器"""

    def get_agent_profile_id(self) -> str:
        return "patent.retrieval_analyst.v1"

    async def execute(self) -> PhaseResult:
        start_time = datetime.now()

        self._logger.info("Starting retrieval analysis phase", task_id=self.context.task_id)

        try:
            factory = _get_agent_factory()
            agent = factory.create_agent(self.get_agent_profile_id())

            # 整合需求分析结果
            req = self.context.requirement_analysis
            input_text = f"""
基于以下需求分析结果，进行专利性评估分析：

技术领域：{req.get('tech_field', 'N/A')}
核心原理：{req.get('core_principle', 'N/A')}
关键创新点：
{json.dumps(req.get('key_innovative_features', []), ensure_ascii=False, indent=2)}

请进行全面的专利性评估，包括新颖性、创造性、实用性分析，以及潜在风险识别。
"""

            # 简化版输出 - 直接使用 LLM 返回结构化数据
            from src.core.llm_client import get_llm_service, LLMMessage

            llm_service = get_llm_service()
            messages = [
                LLMMessage(role="system", content=agent._build_system_prompt()),
                LLMMessage(role="user", content=input_text),
            ]

            output_schema = {
                "type": "object",
                "properties": {
                    "novelty_assessment": {
                        "type": "object",
                        "properties": {
                            "rating": {"type": "string", "enum": ["high", "medium", "low"]},
                            "rationale": {"type": "string"},
                        },
                    },
                    "inventive_step_assessment": {
                        "type": "object",
                        "properties": {
                            "rating": {"type": "string", "enum": ["high", "medium", "low"]},
                            "rationale": {"type": "string"},
                        },
                    },
                    "utility_assessment": {
                        "type": "object",
                        "properties": {
                            "rating": {"type": "string", "enum": ["high", "medium", "low"]},
                            "rationale": {"type": "string"},
                        },
                    },
                    "risk_factors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                            },
                        },
                    },
                    "writing_recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "overall_patentability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "conclusion": {"type": "string"},
                },
            }

            result = await llm_service.structured_output(messages, output_schema)

            self.context.retrieval_report = result

            # 检查专利性等级
            issues = []
            if result.get("overall_patentability") == "low":
                issues.append("专利性评估等级为低，建议重新考虑申请策略")

            critical_risks = [
                r for r in result.get("risk_factors", [])
                if r.get("severity") == "critical"
            ]
            if critical_risks:
                issues.append(f"发现 {len(critical_risks)} 个关键风险需要关注")

            duration = (datetime.now() - start_time).total_seconds()

            return PhaseResult(
                phase=WorkflowPhase.RETRIEVAL,
                success=True,
                duration_seconds=duration,
                output=result,
                issues=issues,
            )

        except LLMError as e:
            self._logger.error("LLM call failed during retrieval analysis", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.RETRIEVAL,
                success=False,
                duration_seconds=duration,
                issues=[f"检索分析阶段LLM调用失败: {str(e)}"],
            )

        except Exception as e:
            self._logger.error("Retrieval analysis phase failed", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.RETRIEVAL,
                success=False,
                duration_seconds=duration,
                issues=[f"检索分析阶段失败: {str(e)}"],
            )


class PatentWritingPhaseExecutor(WorkflowPhaseExecutor):
    """专利撰写阶段执行器"""

    def get_agent_profile_id(self) -> str:
        return "patent.writer.v1"

    async def execute(self) -> PhaseResult:
        start_time = datetime.now()

        self._logger.info("Starting patent writing phase", task_id=self.context.task_id)

        try:
            factory = _get_agent_factory()
            agent = factory.create_agent(self.get_agent_profile_id())

            req = self.context.requirement_analysis
            retrieval = self.context.retrieval_report

            input_text = f"""
基于以下信息撰写专利申请文件：

【技术需求分析】
技术领域：{req.get('tech_field', 'N/A')}
核心原理：{req.get('core_principle', 'N/A')}
技术问题：{req.get('technical_problem', 'N/A')}

关键创新点：
{json.dumps(req.get('key_innovative_features', []), ensure_ascii=False, indent=2)}

有益效果：
{json.dumps(req.get('beneficial_effects', []), ensure_ascii=False, indent=2)}

【检索分析建议】
撰写建议：
{json.dumps(retrieval.get('writing_recommendations', []), ensure_ascii=False, indent=2)}

请按照标准专利格式撰写权利要求书和说明书。
"""

            from src.core.llm_client import get_llm_service, LLMMessage

            llm_service = get_llm_service()
            messages = [
                LLMMessage(role="system", content=agent._build_system_prompt()),
                LLMMessage(role="user", content=input_text),
            ]

            output_schema = {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "object",
                        "properties": {
                            "independent_claim": {"type": "string"},
                            "dependent_claims": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "description": {
                        "type": "object",
                        "properties": {
                            "technical_field": {"type": "string"},
                            "background_art": {"type": "string"},
                            "summary_of_invention": {"type": "string"},
                            "detailed_description": {"type": "string"},
                        },
                    },
                    "abstract": {"type": "string"},
                },
            }

            result = await llm_service.structured_output(messages, output_schema)

            self.context.patent_draft = result

            duration = (datetime.now() - start_time).total_seconds()

            return PhaseResult(
                phase=WorkflowPhase.WRITING,
                success=True,
                duration_seconds=duration,
                output=result,
            )

        except LLMError as e:
            self._logger.error("LLM call failed during patent writing", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.WRITING,
                success=False,
                duration_seconds=duration,
                issues=[f"专利撰写阶段LLM调用失败: {str(e)}"],
            )

        except Exception as e:
            self._logger.error("Patent writing phase failed", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.WRITING,
                success=False,
                duration_seconds=duration,
                issues=[f"专利撰写阶段失败: {str(e)}"],
            )


class QualityReviewPhaseExecutor(WorkflowPhaseExecutor):
    """质量审查阶段执行器"""

    def get_agent_profile_id(self) -> str:
        return "patent.quality_reviewer.v1"

    async def execute(self) -> PhaseResult:
        start_time = datetime.now()

        self._logger.info("Starting quality review phase", task_id=self.context.task_id)

        try:
            factory = _get_agent_factory()
            agent = factory.create_agent(self.get_agent_profile_id())

            draft = self.context.patent_draft

            input_text = f"""
请对以下专利申请文件进行质量审查：

【权利要求书】
独立权利要求：
{draft.get('claims', {}).get('independent_claim', 'N/A')}

从属权利要求数量：{len(draft.get('claims', {}).get('dependent_claims', []))}

【说明书摘要】
{draft.get('abstract', 'N/A')}

请进行全面的质量审查，包括形式合规性、权利要求质量、说明书充分性等。
"""

            from src.core.llm_client import get_llm_service, LLMMessage

            llm_service = get_llm_service()
            messages = [
                LLMMessage(role="system", content=agent._build_system_prompt()),
                LLMMessage(role="user", content=input_text),
            ]

            output_schema = {
                "type": "object",
                "properties": {
                    "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "overall_rating": {"type": "string", "enum": ["excellent", "good", "acceptable", "needs_revision", "poor"]},
                    "formal_compliance": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "number"},
                            "passed": {"type": "boolean"},
                            "issues": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "severity": {"type": "string"},
                                        "location": {"type": "string"},
                                        "description": {"type": "string"},
                                        "suggestion": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                    "recommendation": {"type": "string", "enum": ["approve", "revise", "reject"]},
                    "revision_suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "review_summary": {"type": "string"},
                },
            }

            result = await llm_service.structured_output(messages, output_schema)

            self.context.review_report = result

            issues = []
            if result.get("recommendation") in ["revise", "reject"]:
                issues.append(f"审查结果为 {result['recommendation']}，需要进行修正")

            duration = (datetime.now() - start_time).total_seconds()

            return PhaseResult(
                phase=WorkflowPhase.REVIEW,
                success=True,
                duration_seconds=duration,
                output=result,
                issues=issues,
            )

        except LLMError as e:
            self._logger.error("LLM call failed during quality review", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.REVIEW,
                success=False,
                duration_seconds=duration,
                issues=[f"质量审查阶段LLM调用失败: {str(e)}"],
            )

        except Exception as e:
            self._logger.error("Quality review phase failed", error=str(e), exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return PhaseResult(
                phase=WorkflowPhase.REVIEW,
                success=False,
                duration_seconds=duration,
                issues=[f"质量审查阶段失败: {str(e)}"],
            )


class PatentWorkflowEngine:
    """
    专利申请工作流引擎
    协调各阶段 Agent 完成端到端的专利申请流程
    """

    def __init__(self):
        self._logger = get_logger("patent_workflow")
        self._running_workflows: Dict[str, WorkflowContext] = {}

        # 阶段执行器映射
        self._phase_executors = {
            WorkflowState.BRAINSTORMING: BrainstormingPhaseExecutor,
            WorkflowState.REQUIREMENT_ANALYSIS: RequirementAnalysisPhaseExecutor,
            WorkflowState.RETRIEVAL_ANALYSIS: RetrievalAnalysisPhaseExecutor,
            WorkflowState.PATENT_WRITING: PatentWritingPhaseExecutor,
            WorkflowState.QUALITY_REVIEW: QualityReviewPhaseExecutor,
        }

        # 默认完整工作流序列
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
        执行完整工作流

        Args:
            context: 工作流上下文
            phase_callback: 每个阶段完成后的回调
        """
        self._logger.info(
            "Starting full workflow execution",
            task_id=context.task_id,
            phases_count=len(self._default_workflow_sequence),
        )

        try:
            for phase in self._default_workflow_sequence:
                if not phase.value:
                    continue

                context.current_phase = phase

                # 发布进度事件
                await self._publish_progress_event(context, phase, "running")

                # 执行阶段
                result = await self.execute_phase(context, phase)

                context.add_phase_result(result)

                # 发布阶段完成事件
                await self._publish_progress_event(context, phase, "completed", result)

                # 调用回调
                if phase_callback:
                    if asyncio.iscoroutinefunction(phase_callback):
                        await phase_callback(phase, result)
                    else:
                        phase_callback(phase, result)

                # 检查是否需要中断
                if not result.success:
                    self._logger.error(
                        "Phase failed, stopping workflow",
                        task_id=context.task_id,
                        phase=phase.value,
                        issues=result.issues,
                    )
                    context.current_phase = WorkflowState.FAILED
                    return context

                # 如果审查阶段建议修改，启动迭代
                if phase == WorkflowState.QUALITY_REVIEW:
                    review_result = result.output
                    if review_result.get("recommendation") == "revise" and context.iteration_count < context.max_iterations:
                        self._logger.info(
                            "Starting iteration phase",
                            task_id=context.task_id,
                            iteration=context.iteration_count + 1,
                        )
                        context.current_phase = WorkflowState.ITERATION
                        context.iteration_count += 1

                        # TODO: 执行迭代修正逻辑
                        # 这里简化处理，直接继续

            # 工作流完成
            context.current_phase = WorkflowState.COMPLETED

            self._logger.info(
                "Workflow completed successfully",
                task_id=context.task_id,
                total_phases=len(context.phase_history),
            )

            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=context.task_id)
            raise

        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error(
                "Workflow failed with error",
                task_id=context.task_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def execute_phase(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
    ) -> PhaseResult:
        """执行单个阶段"""
        executor_class = self._phase_executors.get(phase)
        if not executor_class:
            raise ValueError(f"No executor found for phase: {phase}")

        executor = executor_class(context)
        return await executor.execute()

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

        # 如果是用户消息，生成助理回复
        if role == "user" and context.current_phase in [
            WorkflowState.INITIALIZED,
            WorkflowState.BRAINSTORMING,
        ]:
            factory = _get_agent_factory()
            agent = factory.create_agent("patent.brainstorm_partner.v1")

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

            response = await agent.run(prompt)
            context.add_message("assistant", str(response))

            return {
                "role": "assistant",
                "content": str(response),
                "phase": context.current_phase.value,
            }

        return {"status": "added"}

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
        if status == "completed":
            completed_index = self._default_workflow_sequence.index(current_phase) + 1
            return int((completed_index / len(self._default_workflow_sequence)) * 100)
        else:
            current_index = self._default_workflow_sequence.index(current_phase)
            return int((current_index / len(self._default_workflow_sequence)) * 100)

    def cancel_workflow(self, task_id: str) -> bool:
        """取消工作流"""
        context = self._running_workflows.pop(task_id, None)
        if context:
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=task_id)
            return True
        return False


# 全局工作流引擎实例
_global_workflow_engine: Optional[PatentWorkflowEngine] = None


def get_workflow_engine() -> PatentWorkflowEngine:
    """获取全局工作流引擎实例"""
    global _global_workflow_engine
    if _global_workflow_engine is None:
        _global_workflow_engine = PatentWorkflowEngine()
    return _global_workflow_engine
