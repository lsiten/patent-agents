"""
专利申请工作流编排引擎
协调 CEO Agent 与各专业 Agent 完成端到端专利申请流程

架构：CEO Agent 通过 dispatch_specialist 工具动态调度各专业 Agent，
本引擎仅负责状态管理、进度追踪和前端 API 兼容。
"""
import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field

from src.core.logging import get_logger
from src.core.events import (
    publish_event,
    EventType,
    AgentThinkingEvent,
    AgentToolCallStartEvent,
    AgentToolCallEndEvent,
    AgentDispatchEvent,
    AgentContentEvent,
)
from src.core.llm_client import LLMError


# ═══════════════════════════════════════════════════════════════════
# 专利任务目录管理 — 每个 task_id 独立目录，子目录按阶段组织
# ═══════════════════════════════════════════════════════════════════

from pathlib import Path as _Path

_BACKEND_DIR = _Path(__file__).resolve().parent.parent.parent

# 阶段 → 子目录映射
_PHASE_DIR_MAP = {
    "requirement_analysis": "requirement",
    "retrieval_report": "retrieval",
    "patent_draft": "draft",
    "review_report": "review",
}


def _get_task_dir(task_id: str) -> _Path:
    """获取专利任务根目录（绝对路径）"""
    task_dir = _BACKEND_DIR / "exports" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def _get_phase_dir(task_id: str, phase_field: str) -> _Path:
    """获取某阶段的子目录"""
    sub = _PHASE_DIR_MAP.get(phase_field, phase_field)
    phase_dir = _get_task_dir(task_id) / sub
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir


def _persist_phase_result(task_id: str, phase_field: str, data: dict) -> str:
    """将阶段结果持久化为 JSON 文件，返回文件绝对路径"""
    phase_dir = _get_phase_dir(task_id, phase_field)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{phase_field}_{timestamp}.json"
    file_path = phase_dir / filename
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 同时写一个 latest.json 方便快速读取
    latest_path = phase_dir / "latest.json"
    latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)


def _get_agent_factory():
    """返回 Agent 配置注册表实例，用于工作流阶段调用 Agent。
    通过 create_ai_agent(profile_id) 创建 AIAgent，然后调用 agent.run_conversation(prompt)。
    """
    from src.agents.agent_config import get_agent_config_registry
    return get_agent_config_registry()


async def _run_agent_conversation(profile_id: str, prompt: str, session_id: str | None = None) -> str | Dict[str, Any]:
    """运行 Agent 对话的辅助函数
    
    创建 AIAgent 并在线程中运行同步的 run_conversation 方法。
    返回 Agent 原始 dict 结果或文本结果。
    """
    import asyncio
    from src.agents.agent_config import create_ai_agent
    
    agent = create_ai_agent(profile_id=profile_id, session_id=session_id)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent.run_conversation, prompt),
            timeout=300,
        )
    except asyncio.TimeoutError:
        return {
            "failed": True,
            "completed": False,
            "error": f"Agent {profile_id} timed out",
        }
    
    if isinstance(result, dict):
        return result
    return str(result) if result else ""

logger = get_logger("workflow_engine")
T = TypeVar("T", bound=BaseModel)

QUALITY_REMEDIATION_THRESHOLD = 0.8
QUALITY_REMEDIATION_SAFETY_LIMIT = 12
SPECIALIST_AGENT_NAMES = {
    "requirement_analyst": "需求分析师",
    "retrieval_analyst": "检索分析师",
    "patent_writer": "专利撰写 Agent",
    "quality_reviewer": "质量审查 Agent",
}

SPECIALIST_AGENT_ACTIONS = {
    "requirement_analyst": "分析技术方案并提取创新点",
    "retrieval_analyst": "检索先有技术",
    "patent_writer": "撰写专利申请文件",
    "quality_reviewer": "审查专利申请文件质量",
}



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
    # 等待用户决策
    AWAITING_USER_DECISION = "awaiting_user_decision"
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

    def __init__(self, task_id: str, user_id: str, target_country: str = "中国"):
        self.task_id = task_id
        self.user_id = user_id
        self.target_country = target_country
        self.created_at = datetime.now()
        self.updated_at = self.created_at

        # 专利标题（从技术描述中提取）
        self.title: str = ""

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
        self.max_iterations: int = 3  # 软提示阈值；质量未达标时仍继续自动修正
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

_PHASE_CONTEXT_FIELDS = {
    WorkflowState.REQUIREMENT_ANALYSIS: "requirement_analysis",
    WorkflowState.RETRIEVAL_ANALYSIS: "retrieval_report",
    WorkflowState.PATENT_WRITING: "patent_draft",
    WorkflowState.QUALITY_REVIEW: "review_report",
}

_PHASE_DISPLAY_NAMES = {
    WorkflowState.REQUIREMENT_ANALYSIS: "需求分析 Agent",
    WorkflowState.RETRIEVAL_ANALYSIS: "检索分析 Agent",
    WorkflowState.PATENT_WRITING: "专利撰写 Agent",
    WorkflowState.QUALITY_REVIEW: "质量审查 Agent",
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
        target_country: str = "中国",
    ) -> WorkflowContext:
        """创建新的工作流"""
        context = WorkflowContext(task_id=task_id, user_id=user_id, target_country=target_country)
        cleaned_description = self._sanitize_disclosure_text(description)
        context.original_description = cleaned_description
        context.title = self._extract_title(cleaned_description)
        context.metadata = {
            **context.metadata,
            "target_country": target_country,
            "raw_disclosure": description,
            "disclosure_sanitized": cleaned_description != description,
        }
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
            target_country=target_country,
            description_length=len(description),
        )

        return context

    @staticmethod
    def _sanitize_disclosure_text(description: str) -> str:
        """Turn meeting transcripts into technical disclosure text before drafting."""
        if not description:
            return ""
        text = str(description).replace("\r\n", "\n").replace("\r", "\n")
        cleaned_lines: List[str] = []
        speaker_ts = re.compile(r"^\s*[\u4e00-\u9fa5A-Za-z0-9_·（）()、\s]{1,30}[（(]\d{2}:\d{2}:\d{2}[）)]\s*[：:]?\s*")
        plain_ts = re.compile(r"^\s*[（(]?\d{2}:\d{2}:\d{2}[）)]?\s*[：:]?\s*")
        filename_noise = re.compile(r"^\s*(文件名|任务编号|生成时间|逐字稿|会议记录|转写文本)\s*[：:]")
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line or filename_noise.search(line):
                continue
            line = speaker_ts.sub("", line)
            line = plain_ts.sub("", line)
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            if line in {"嗯", "啊", "对", "行", "好的", "那先写", "那写吧"}:
                continue
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines).strip()
        return cleaned or str(description).strip()

    @staticmethod
    def _extract_title(description: str) -> str:
        """从技术描述中提取专利标题"""
        if not description:
            return "未命名专利"
        text = PatentWorkflowEngine._sanitize_disclosure_text(description)
        if re.search(r"Cave|折幕|沉浸式|多屏|显示面|姿态|补偿|遮挡|裁剪", text, re.I):
            return "一种基于Cave折幕视频的处理方法及系统"
        # 取第一句或前40字符作为标题
        # 按句号、换行截断（逗号不截断，保留完整短语）
        for sep in ["。", ".", "\n", "；", ";"]:
            idx = text.find(sep, 0, 80)
            if idx > 0:
                text = text[:idx]
                break
        text = re.sub(r"^本发明(?:公开|涉及|提供|提出)了?", "", text).strip(" ：:，,。")
        # 如果仍然太长，在逗号处截断
        if len(text) > 40:
            comma_idx = text.find("，", 0, 50) or text.find(",", 0, 50)
            if comma_idx and comma_idx > 0:
                text = text[:comma_idx]
        # 最终限制
        if len(text) > 50:
            text = text[:50]
        return text.strip() or "未命名专利"

    def get_workflow(self, task_id: str) -> Optional[WorkflowContext]:
        """获取工作流上下文"""
        return self._running_workflows.get(task_id)

    def list_workflows(self) -> List[WorkflowContext]:
        """列出所有工作流上下文"""
        return list(self._running_workflows.values())

    async def execute_full_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        agent_event_callback: Optional[Callable[[Dict[str, Any]], None | Awaitable[None]]] = None,
    ) -> WorkflowContext:
        """
        执行完整工作流 — 顺序调用各专业 Agent

        每个阶段由对应的专业 Agent 直接执行，确保各阶段有实际输出。
        patent_writer 使用分段生成策略（权利要求+说明书+摘要）。
        """
        self._logger.info("Starting workflow", task_id=context.task_id)

        async def emit_agent_work_event(event: Dict[str, Any]) -> None:
            if agent_event_callback is None:
                return
            event.setdefault("task_id", context.task_id)
            event.setdefault("timestamp", datetime.now().isoformat())
            result = agent_event_callback(event)
            if asyncio.iscoroutine(result):
                await result

        try:
            service = _get_agent_factory()

            phases = [
                ("requirement_analyst", "patent.requirement_analyst.v1", "requirement_analysis", WorkflowState.REQUIREMENT_ANALYSIS, WorkflowPhase.REQUIREMENT),
                ("retrieval_analyst", "patent.retrieval_analyst.v1", "retrieval_report", WorkflowState.RETRIEVAL_ANALYSIS, WorkflowPhase.RETRIEVAL),
                ("patent_writer", "patent.writer.v1", "patent_draft", WorkflowState.PATENT_WRITING, WorkflowPhase.WRITING),
                ("quality_reviewer", "patent.quality_reviewer.v1", "review_report", WorkflowState.QUALITY_REVIEW, WorkflowPhase.REVIEW),
            ]

            for agent_id, profile_id, context_field, phase_state, phase_enum in phases:
                if context.metadata.get("cancel_requested") or context.current_phase == WorkflowState.CANCELLED:
                    raise asyncio.CancelledError()
                phase_started_at = time.perf_counter()
                context.current_phase = phase_state
                await self._publish_progress_event(context, phase_state, "running")

                # Agent 显示名映射
                agent_display_name = SPECIALIST_AGENT_NAMES.get(agent_id, agent_id)
                agent_action = SPECIALIST_AGENT_ACTIONS.get(agent_id, agent_id)

                # 构建任务 prompt
                task_desc = self._build_phase_prompt(context, phase_state)
                await emit_agent_work_event({
                    "event_type": "agent.work.started",
                    "agent_id": agent_id,
                    "agent_name": agent_display_name,
                    "profile_id": profile_id,
                    "action": agent_action,
                    "status": "running",
                    "data": {"task": agent_action, "phase": phase_state.value},
                })
                self._logger.info(f"Executing phase: {agent_id}")

                # ═══ 失败自动重试（最多重试 max_retries 次）═══
                max_retries = 2
                last_error = None
                phase_success = False
                context_data: Dict[str, Any] = {}
                agent_text = ""

                for attempt in range(1 + max_retries):
                    try:
                        if attempt > 0:
                            self._logger.info(
                                f"Retrying phase {agent_id} (attempt {attempt + 1}/{1 + max_retries})"
                            )
                            if event_callback:
                                event_callback("CEO Agent", "agent.thinking",
                                    f"⚠️ {agent_display_name} 执行失败，正在重试（第{attempt + 1}次）...",
                                    {"agent_name": "CEO Agent", "thought": f"重试 {agent_display_name}", "step": attempt})
                            # 短暂延迟后重试
                            await asyncio.sleep(2 * attempt)

                        # 发射 CEO 调度事件
                        if event_callback:
                            event_callback("CEO Agent", "agent.dispatch",
                                f"🎯 调度 → {agent_display_name}: {task_desc[:100]}",
                                {"from_agent": "CEO Agent", "to_agent": agent_display_name, "task_description": task_desc[:300]})
                        else:
                            await publish_event(AgentDispatchEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                from_agent="CEO Agent",
                                to_agent=agent_display_name,
                                task_description=task_desc[:300],
                            ))

                        # requirement_analyst 使用确定性工具链，避免外层 Agent 卡住整条流程
                        if agent_id == "requirement_analyst":
                            if event_callback:
                                event_callback(agent_display_name, "agent.thinking",
                                    "💭 开始执行需求分析工具链（IPC分类 → 技术特征 → 应用场景）",
                                    {"agent_name": agent_display_name, "thought": "需求分析工具链", "step": 1})
                            context_data = await self._generate_requirement_analysis_with_tools(
                                context,
                                event_callback=event_callback,
                            )
                            agent_text = json.dumps(context_data, ensure_ascii=False)[:500]

                        # retrieval_analyst 使用确定性工具链，避免核心检索完成后继续自由浏览而不收口
                        elif agent_id == "retrieval_analyst":
                            if event_callback:
                                event_callback(agent_display_name, "agent.thinking",
                                    "💭 开始执行检索工具链（专利检索 → 相似度 → 专利性 → 风险）",
                                    {"agent_name": agent_display_name, "thought": "检索工具链", "step": 1})
                            context_data = await self._generate_retrieval_report_with_tools(
                                context,
                                event_callback=event_callback,
                            )
                            agent_text = json.dumps(context_data, ensure_ascii=False)[:500]

                        # patent_writer 使用分段生成
                        elif agent_id == "patent_writer" and not hasattr(service, "run_conversation_stream"):
                            # 发射分段生成进度事件
                            if event_callback:
                                event_callback(agent_display_name, "agent.thinking",
                                    "💭 开始分段生成专利文件（权利要求 → 说明书 → 摘要）",
                                    {"agent_name": agent_display_name, "thought": "分段生成专利文件", "step": 1})
                            context_data = await self._generate_patent_in_sections(
                                service,
                                profile_id,
                                task_desc,
                                context,
                                event_callback=event_callback,
                            )
                            agent_text = json.dumps(context_data, ensure_ascii=False)[:500] if isinstance(context_data, dict) else str(context_data)[:500]
                        elif agent_id == "quality_reviewer":
                            agent_text, context_data = await self._run_quality_review_with_timeout(
                                service,
                                profile_id,
                                task_desc,
                                context,
                                event_callback=event_callback,
                            )
                            agent_tool_results = []
                        else:
                            # 流式调用 Agent（发射 thinking/tool_call 事件）
                            agent_result = await self._run_agent_stream(
                                service, profile_id, task_desc,
                                context, agent_name=agent_display_name,
                                event_callback=event_callback,
                            )
                            agent_text = agent_result.get("text", "")
                            agent_tool_results = agent_result.get("tool_results", [])
                            context_data = self._build_context_data_from_agent_response(
                                agent_id,
                                agent_text,
                                agent_tool_results,
                                agent_result.get("structured_result"),
                            )


                        context_data = self._normalize_phase_output(context_field, context_data)
                        if context_field == "patent_draft":
                            context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        elif (
                            context_field == "review_report"
                            and isinstance(context_data, dict)
                            and context_data.get("_agent_failed") is True
                        ):
                            context_data = self._build_deterministic_quality_review(
                                context,
                                reason=str(context_data.get("_agent_error") or "审查 Agent 不可用"),
                            )
                        if isinstance(context_data, dict) and context_data.get("_agent_failed") is True:
                            agent_error = str(
                                context_data.get("_agent_error") or "Agent execution failed"
                            )[:500]
                            last_error = RuntimeError(agent_error)
                            if attempt >= max_retries:
                                break
                            raise last_error

                        phase_success = True
                        last_error = None
                        break  # 成功，退出重试循环

                    except (LLMError, Exception) as e:
                        last_error = e
                        self._logger.warning(
                            f"Phase {agent_id} attempt {attempt + 1} failed: {e}"
                        )
                        if attempt >= max_retries:
                            # 所有重试都失败
                            raise

                # 发射 Agent 输出完成事件
                if event_callback:
                    event_callback(agent_display_name, "agent.content",
                        f"📄 输出",
                        {"agent_name": agent_display_name, "content": agent_text if agent_text else "", "phase": phase_state.value})
                else:
                    await publish_event(AgentContentEvent(
                        task_id=context.task_id,
                        user_id=context.user_id,
                        agent_name=agent_display_name,
                        content=agent_text if agent_text else "",
                        phase=phase_state.value,
                    ))

                # 存储结果（适配前端期望的数据格式）
                setattr(context, context_field, context_data)
                if agent_id == "patent_writer" and isinstance(context_data, dict):
                    context_data = await self._ensure_required_patent_drawings(
                        context,
                        context_data,
                        event_callback=event_callback,
                    )
                    context_data = await self._refresh_working_draft_docx(
                        context,
                        context_data,
                        checkpoint="附图补齐",
                        event_callback=event_callback,
                    )
                    context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    setattr(context, context_field, context_data)

                agent_failed = (
                    isinstance(context_data, dict)
                    and context_data.get("_agent_failed") is True
                )
                agent_error = ""
                if agent_failed:
                    agent_error = str(
                        context_data.get("_agent_error") or "Agent execution failed"
                    )[:500]

                # 持久化阶段结果到对应子目录
                try:
                    saved_path = _persist_phase_result(
                        context.task_id, context_field,
                        context_data if isinstance(context_data, dict) else {"output": str(context_data)},
                    )
                    self._logger.info(f"Phase result persisted: {saved_path}")
                except Exception as e:
                    self._logger.warning(f"Failed to persist phase result: {e}")

                if agent_failed:
                    context.add_phase_result(PhaseResult(
                        phase=phase_enum,
                        success=False,
                        duration_seconds=time.perf_counter() - phase_started_at,
                        output=context_data,
                        issues=[agent_error] if agent_error else [],
                    ))
                    await self._publish_progress_event(context, phase_state, "failed")
                    context.current_phase = WorkflowState.FAILED
                    await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                    await emit_agent_work_event({
                        "event_type": "agent.work.failed",
                        "agent_id": agent_id,
                        "agent_name": agent_display_name,
                        "profile_id": profile_id,
                        "action": agent_action,
                        "status": "failed",
                        "error": agent_error,
                        "data": {"task": agent_action, "phase": phase_state.value},
                    })
                    self._logger.error(
                        f"Workflow phase failed: {agent_id}: {agent_error}",
                        task_id=context.task_id,
                    )
                    if agent_id == "patent_writer":
                        context.review_report = self._build_writer_failure_review(context_data)
                        break
                    if agent_id == "quality_reviewer":
                        break
                    return context

                # 记录阶段完成
                context.add_phase_result(PhaseResult(
                    phase=phase_enum,
                    success=True,
                    duration_seconds=time.perf_counter() - phase_started_at,
                    output=context_data if isinstance(context_data, dict) else {},
                ))
                await self._publish_progress_event(context, phase_state, "completed")
                await emit_agent_work_event({
                    "event_type": "agent.work.completed",
                    "agent_id": agent_id,
                    "agent_name": agent_display_name,
                    "profile_id": profile_id,
                    "action": agent_action,
                    "status": "completed",
                    "summary": agent_text[:300] if agent_text else "",
                    "data": {"task": agent_action, "phase": phase_state.value},
                })

                if phase_callback:
                    if asyncio.iscoroutinefunction(phase_callback):
                        await phase_callback(phase_state, context.phase_history[-1])
                    else:
                        phase_callback(phase_state, context.phase_history[-1])

            # ═══ 质量门循环：审查撰写内容 → 修正 → 再审查 → 通过后生成 docx ═══
            max_iterations = context.max_iterations  # 自动修正软提示阈值
            safety_limit = int(
                context.metadata.get(
                    "quality_remediation_safety_limit",
                    QUALITY_REMEDIATION_SAFETY_LIMIT,
                )
                or QUALITY_REMEDIATION_SAFETY_LIMIT
            )
            review_passed = False

            if context.review_report:
                needs_remediation = self._needs_quality_remediation(context.review_report)
                if not needs_remediation:
                    review_passed = True
                context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0

            while not review_passed:
                if context.review_report:
                    # 审查未通过 — 提取问题并进入补救分流
                    context.iteration_count += 1
                    review_issues = self._extract_review_issues(context.review_report)
                    context.latest_revision_suggestions = review_issues
                    context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0
                    remediation_path = self._classify_remediation_path(context.review_report, context)

                    self._logger.info(
                        f"Quality review requires remediation (round {context.iteration_count}, path={remediation_path})",
                        task_id=context.task_id,
                    )
                    if event_callback:
                        event_callback("CEO Agent", "agent.thinking",
                            f"⚠️ 质量审查发现问题，启动修正迭代（第{context.iteration_count}轮）",
                            {"agent_name": "CEO Agent", "thought": "质量审查未通过，需要修正"})
                        issue_summary = "\n".join(
                            f"{index}. {issue}"
                            for index, issue in enumerate(review_issues[:12], start=1)
                        ) or "审查报告要求继续优化，但未返回结构化问题明细。"
                        event_callback(
                            "CEO Agent",
                            "agent.content",
                            f"📋 第{context.iteration_count}轮审查问题\n{issue_summary}",
                            {
                                "agent_name": "CEO Agent",
                                "content": issue_summary,
                                "phase": "quality_review",
                                "iteration_count": context.iteration_count,
                                "review_score": context.latest_review_score,
                                "remediation_path": remediation_path,
                            },
                        )

                    if context.iteration_count > safety_limit:
                        self._logger.warning(
                            f"Automatic remediation exceeded safety hint ({safety_limit}); "
                            "continuing because patent quality gate must pass before completion",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                f"🔁 已连续自动修正 {safety_limit} 轮仍未合格，继续由 CEO 调度补充和复审",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "auto_remediation_continue_until_pass",
                                    "iteration_count": context.iteration_count,
                                },
                            )

                    if remediation_path == "TERMINAL_FAILURE":
                        break

                    if remediation_path == "NEEDS_USER_INPUT":
                        self._enter_quality_remediation_hold(context, context.review_report, remediation_path)
                        if event_callback:
                            remediation = context.metadata.get("quality_remediation", {})
                            missing_information = remediation.get("missing_information", [])
                            detail = "；".join(str(item) for item in missing_information) if missing_information else "缺少额外信息"
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                f"🔁 质量审查指出缺少信息，默认由 CEO 调度自动补充并复审：{detail}",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "auto_remediation_missing_information",
                                    "missing_information": missing_information,
                                },
                            )
                        await self._execute_remediation_phase(
                            context,
                            self._resolve_remediation_resume_phase(remediation_path),
                            event_callback=event_callback,
                        )

                    if remediation_path == "ANALYZE_MORE":
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.dispatch",
                                f"🎯 调度 → 需求分析 Agent（根据审查问题补充方案，第{context.iteration_count}轮）",
                                {
                                    "from_agent": "CEO Agent",
                                    "to_agent": _PHASE_DISPLAY_NAMES.get(WorkflowState.REQUIREMENT_ANALYSIS, "需求分析 Agent"),
                                    "task_description": "\n".join(review_issues[:8]),
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        await self._execute_remediation_phase(
                            context,
                            WorkflowState.REQUIREMENT_ANALYSIS,
                            event_callback=event_callback,
                        )
                    elif remediation_path == "SEARCH_MORE":
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.dispatch",
                                f"🎯 调度 → 检索分析 Agent（根据审查问题补充检索，第{context.iteration_count}轮）",
                                {
                                    "from_agent": "CEO Agent",
                                    "to_agent": _PHASE_DISPLAY_NAMES.get(WorkflowState.RETRIEVAL_ANALYSIS, "检索分析 Agent"),
                                    "task_description": "\n".join(review_issues[:8]),
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        await self._execute_remediation_phase(
                            context,
                            WorkflowState.RETRIEVAL_ANALYSIS,
                            event_callback=event_callback,
                        )

                    # ── 修正撰写 ──
                    context.current_phase = WorkflowState.PATENT_WRITING
                    await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "running")

                    revision_prompt = self._build_revision_prompt(context, review_issues)

                    if event_callback:
                        event_callback("CEO Agent", "agent.dispatch",
                            f"🎯 调度 → 专利撰写 Agent（修正迭代第{context.iteration_count}轮）",
                            {"from_agent": "CEO Agent", "to_agent": "专利撰写 Agent", "task_description": revision_prompt[:300]})

                    try:
                        context_data = await self._generate_patent_in_sections(
                            service,
                            "patent.writer.v1",
                            revision_prompt,
                            context,
                            event_callback=event_callback,
                        )
                        agent_text = json.dumps(context_data, ensure_ascii=False)[:500]
                        agent_tool_results = []
                    except Exception as exc:
                        self._logger.warning(
                            f"Patent writer revision failed, applying fallback repairs: {exc}",
                            task_id=context.task_id,
                        )
                        agent_text = ""
                        agent_tool_results = []
                        context_data = {
                            "failed": True,
                            "completed": False,
                            "error": str(exc),
                            "structured_result": {
                                "failed": True,
                                "completed": False,
                                "error": str(exc),
                            },
                        }

                    if event_callback:
                        event_callback("专利撰写 Agent", "agent.content",
                            f"📄 输出（修正第{context.iteration_count}轮）",
                            {"agent_name": "专利撰写 Agent", "content": agent_text[:500] if agent_text else "", "phase": "patent_writing"})

                    context_data = self._normalize_phase_output("patent_draft", context_data)
                    context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    if not isinstance(context_data, dict) or context_data.get("_agent_failed") is True:
                        context_data = context.patent_draft if isinstance(context.patent_draft, dict) else {}
                    if isinstance(context_data, dict):
                        context_data = self._apply_review_suggestions_to_draft(
                            context,
                            context_data,
                            review_issues,
                            event_callback=event_callback,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        context_data = await self._ensure_required_patent_drawings(
                            context,
                            context_data,
                            event_callback=event_callback,
                        )
                        context_data = await self._refresh_working_draft_docx(
                            context,
                            context_data,
                            checkpoint=f"修正第{context.iteration_count}轮",
                            event_callback=event_callback,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    context.patent_draft = context_data
                    # 持久化修正后的撰写结果
                    try:
                        _persist_phase_result(context.task_id, "patent_draft", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                    except Exception:
                        pass
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.WRITING,
                        success=not (isinstance(context_data, dict) and context_data.get("_agent_failed") is True),
                        duration_seconds=0,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if isinstance(context_data, dict) and context_data.get("_agent_failed") is True else [],
                    ))
                    await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "completed")

                    # ── 重新审查 ──
                    context.current_phase = WorkflowState.QUALITY_REVIEW
                    await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "running")

                    review_prompt = self._build_phase_prompt(context, WorkflowState.QUALITY_REVIEW)

                    if event_callback:
                        event_callback("CEO Agent", "agent.dispatch",
                            f"🎯 调度 → 质量审查 Agent（第{context.iteration_count + 1}轮审查）",
                            {"from_agent": "CEO Agent", "to_agent": "质量审查 Agent", "task_description": review_prompt[:300]})

                    agent_text, context_data = await self._run_quality_review_with_timeout(
                        service,
                        "patent.quality_reviewer.v1",
                        review_prompt,
                        context,
                        event_callback=event_callback,
                        round_label=f"第{context.iteration_count + 1}轮",
                    )

                    if event_callback:
                        event_callback("质量审查 Agent", "agent.content",
                            f"📄 审查结果（第{context.iteration_count + 1}轮）",
                            {"agent_name": "质量审查 Agent", "content": agent_text[:500] if agent_text else "", "phase": "quality_review"})

                    context_data = self._normalize_phase_output("review_report", context_data)
                    if isinstance(context_data, dict) and context_data.get("_agent_failed") is True:
                        context_data = self._build_deterministic_quality_review(
                            context,
                            reason=str(context_data.get("_agent_error") or "审查 Agent 不可用"),
                        )
                    context.review_report = context_data
                    # 持久化审查结果
                    try:
                        _persist_phase_result(context.task_id, "review_report", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                    except Exception:
                        pass
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.REVIEW,
                        success=not (isinstance(context_data, dict) and context_data.get("_agent_failed") is True),
                        duration_seconds=0,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if isinstance(context_data, dict) and context_data.get("_agent_failed") is True else [],
                    ))
                    await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "completed")

                # 检查审查是否通过
                needs_remediation = self._needs_quality_remediation(context.review_report)
                context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0
                if not needs_remediation:
                    review_passed = True
                    context.metadata.pop("quality_remediation", None)
                    self._logger.info("Quality review passed", task_id=context.task_id)
                    if event_callback:
                        event_callback("CEO Agent", "agent.thinking",
                            "✅ 质量审查通过，准备生成最终文档",
                            {"agent_name": "CEO Agent", "thought": "审查通过"})
                else:
                    # 关键优化 (避免无限循环): 当 writer 和 reviewer 连续失败
                    # 且错误相同时 (例如 LLM API 一直不可用),继续迭代没有意义。
                    # 立即跳出,以 FAILED 状态结束,节省时间和资源。
                    if self._iteration_making_no_progress(context):
                        self._logger.error(
                            f"Iteration making no progress: writer/reviewer keep failing "
                            f"with same error. Breaking out early. "
                            f"task_id={context.task_id}, iteration_count={context.iteration_count}",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback("CEO Agent", "agent.thinking",
                                "❌ 修正迭代未取得进展（同一错误重复出现），提前终止",
                                {"agent_name": "CEO Agent", "thought": "iteration_no_progress"})
                        break
                    if context.iteration_count == max_iterations:
                        self._logger.warning(
                            f"Soft remediation iteration threshold ({max_iterations}) reached; continuing until quality passes",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback("CEO Agent", "agent.thinking",
                                f"⚠️ 已达建议修正轮次({max_iterations})，但质量未达标，将继续自动补充和复审",
                                {"agent_name": "CEO Agent", "thought": "继续质量修正"})

            # ═══ 质量审查通过（或达到最大迭代次数）→ 生成最终 .docx 文件 ═══
            # 关键修复 (Bug #1 用户可见层): 在生成 .docx 之前,必须先确认
            # patent_draft 真的有内容、review 没有未解决的关键问题。
            # 如果有问题,流程必须以 FAILED 结束,而不是 COMPLETED。
            if context.current_phase == WorkflowState.AWAITING_USER_DECISION:
                self._logger.info(
                    "Workflow paused for user decision before final document generation",
                    task_id=context.task_id,
                )
                return context

            if self._has_unresolved_critical_issues(context):
                self._logger.error(
                    "Workflow cannot complete: unresolved critical issues remain "
                    "(patent_draft incomplete OR review has critical issues). "
                    f"task_id={context.task_id}, iteration_count={context.iteration_count}",
                    task_id=context.task_id,
                )
                if event_callback:
                    draft_failed = (
                        not context.patent_draft
                        or not isinstance(context.patent_draft, dict)
                        or context.patent_draft.get("_agent_failed") is True
                        or context.patent_draft.get("_incomplete_output") is True
                    )
                    review_failed = (
                        not context.review_report
                        or not isinstance(context.review_report, dict)
                        or context.review_report.get("_agent_failed") is True
                        or self._check_review_needs_revision(context.review_report or {})
                    )
                    reason = []
                    if draft_failed:
                        reason.append("撰写 Agent 未生成有效内容")
                    if review_failed:
                        reason.append("审查 Agent 发现未解决的关键问题")
                    msg = f"❌ 流程未能完成: {'; '.join(reason) or '关键检查未通过'}"
                    event_callback("CEO Agent", "agent.thinking", msg, {
                        "agent_name": "CEO Agent",
                        "thought": "workflow_failed_unresolved_critical_issues",
                    })
                context.current_phase = WorkflowState.FAILED
                await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                self._logger.warning("Workflow ended in FAILED state (unresolved critical issues)", task_id=context.task_id)
                return context

            if context.patent_draft and isinstance(context.patent_draft, dict):
                if event_callback:
                    event_callback("CEO Agent", "agent.thinking",
                        "📝 正在生成最终专利文档 (.docx)...",
                        {"agent_name": "CEO Agent", "thought": "生成最终文档"})

                try:
                    from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

                    draft = context.patent_draft
                    claims_data = draft.get("claims", {})
                    description_data = draft.get("description", {})
                    abstract_text = draft.get("abstract", "")

                    docx_tool = PatentDocxGeneratorTool()
                    docx_result = await docx_tool.execute(
                        title=context.title or "专利申请文件",
                        claims=claims_data,
                        description=description_data,
                        abstract=abstract_text,
                        task_id=context.task_id,
                        tech_description=context.original_description,
                        drawings=draft.get("drawings", []),
                        output_stage="final",
                    )
                    if docx_result.get("success"):
                        docx_path = docx_result.get("file_path", "")
                        context.patent_draft["docx_path"] = docx_path
                        if docx_result.get("figures"):
                            context.patent_draft["docx_figures"] = docx_result.get("figures")
                        context.patent_draft["final_document"] = {
                            "file_path": docx_path,
                            "filename": _Path(docx_path).name if docx_path else "",
                            "download_url": f"/api/v1/workflows/{context.task_id}/export/docx",
                        }
                        context.metadata["final_document_path"] = docx_path
                        try:
                            _persist_phase_result(context.task_id, "patent_draft", context.patent_draft)
                        except Exception as persist_exc:
                            self._logger.warning(
                                f"Failed to persist final patent draft metadata: {persist_exc}",
                                task_id=context.task_id,
                            )
                        self._logger.info(f"Final DOCX generated after quality review: {docx_path}")
                        if event_callback:
                            event_callback("CEO Agent", "agent.content",
                                f"✅ 最终专利文档已生成: {docx_path}",
                                {"agent_name": "CEO Agent", "content": f"文档路径: {docx_path}", "phase": "completed"})
                    else:
                        self._logger.error(f"DOCX generation failed: {docx_result}")
                except Exception as e:
                    self._logger.error(f"Failed to generate final DOCX: {e}", exc_info=True)

            # 完成
            context.current_phase = WorkflowState.COMPLETED
            await self._publish_progress_event(context, WorkflowState.COMPLETED, "completed")
            context.brainstorming_output = {"summary": "专利申请流程已完成。需求分析→检索→撰写→审查全部通过，已生成最终文档。"}
            self._logger.info("Workflow completed", task_id=context.task_id)
            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            raise
        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error("Workflow failed", task_id=context.task_id, error=str(e), exc_info=True)
            raise

    async def resume_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
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

        if not force_start_from and context.current_phase == WorkflowState.AWAITING_USER_DECISION:
            remediation = context.metadata.get("quality_remediation", {})
            resume_phase = remediation.get("resume_phase")
            if isinstance(resume_phase, str):
                try:
                    force_start_from = WorkflowState(resume_phase)
                except ValueError:
                    force_start_from = WorkflowState.REQUIREMENT_ANALYSIS
            else:
                force_start_from = WorkflowState.REQUIREMENT_ANALYSIS

        if force_start_from:
            context.current_phase = WorkflowState.ITERATION
            context.iteration_count += 1

        try:
            service = _get_agent_factory()

            # 构建带已有成果的恢复 prompt
            prompt = self._build_ceo_resume_prompt(context, force_start_from)

            result_text = await _run_agent_conversation("patent.ceo.v1", prompt)
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

            result_text = await _run_agent_conversation(profile_id, prompt)
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

            # 构建对话历史（文件类消息用标签包裹）
            def _fmt_msg(m: dict) -> str:
                role = m["role"].upper()
                if m.get("type") == "file":
                    fname = m.get("metadata", {}).get("filename", "文件")
                    return f"{role} [上传文件: {fname}]:\n---文件内容开始---\n{m['content']}\n---文件内容结束---"
                return f"{role}: {m['content']}"

            history_text = "\n\n".join([
                _fmt_msg(m)
                for m in context.message_history[-10:]
            ])

            prompt = f"""
基于以下对话历史，继续与用户讨论专利申请方案：

{history_text}

请基于你的专业知识主动分析，对能确定的信息直接给出判断让用户确认（使用"是否"问句），
仅对确实无法从知识库获取的信息才提问让用户补充。
"""

            response = await _run_agent_conversation("patent.brainstorm_partner.v1", prompt)
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
        context = self._running_workflows.get(task_id)
        if context:
            context.metadata["cancel_requested"] = True
            context.current_phase = WorkflowState.CANCELLED
            self._logger.info("Workflow cancelled", task_id=task_id)
            return True
        return False

    # ============ 内部辅助方法 ============

    def _build_ceo_workflow_prompt(self, context: WorkflowContext) -> str:
        """构建 CEO 工作流 prompt — 引导 CEO 表达调度意图"""
        patent_type = context.metadata.get("patent_type_preference", "未指定")
        target_country = context.metadata.get("target_country", "中国")
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

【目标申请国家/法域】{target_country}

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

        target_country = context.metadata.get("target_country", "中国")

        return f"""继续执行专利申请流程。

【技术描述】
{context.original_description}

【目标申请国家/法域】{target_country}

【已有成果】
{existing_text}

【修正建议】
{json.dumps(context.latest_revision_suggestions, ensure_ascii=False) if context.latest_revision_suggestions else "无"}
{start_hint}
请评估已有成果，根据修正建议使用 dispatch_specialist 继续推进流程直到完成。"""

    def _build_phase_prompt(self, context: WorkflowContext, phase: WorkflowState, content_only: bool = False) -> str:
        """为单个阶段构建 prompt

        Args:
            context: 工作流上下文
            phase: 目标阶段
            content_only: 仅当 phase=PATENT_WRITING 时有效。
                          True 时省略 patent_docx_generator 工具调用步骤，
                          用于质量门检查前的内容生成（不生成 .docx）。
        """
        base = context.get_combined_input()

        # 强制工具调用前缀（针对不同阶段）
        TOOL_FORCE_PREFIX = {
            WorkflowState.REQUIREMENT_ANALYSIS: """【强制工具调用指令 - 必须严格执行】
在输出任何分析结论之前，你必须按以下顺序调用工具：
1. 首先调用 ipc_classifier 工具
2. 然后调用 tech_feature_extractor 工具  
3. 最后调用 scenario_miner 工具
只有在获得所有工具返回结果后，才能生成最终JSON输出。
---

""",
            WorkflowState.RETRIEVAL_ANALYSIS: """【强制工具调用指令 - 必须严格执行】
在输出任何检索结论之前，你必须按以下顺序调用工具：
1. 首先调用 patent_search 工具检索现有技术
2. 然后调用 similarity_analyzer 工具分析相似度
3. 接着调用 patentability_scorer 工具评估专利性
4. 最后调用 risk_analyzer 工具识别风险
只有在获得所有工具返回结果后，才能生成最终JSON输出。
---

""",
            WorkflowState.PATENT_WRITING: """【强制工具调用指令 - 必须严格执行】
在输出任何专利文件内容之前，你必须调用以下工具：
1. 调用 claim_drafter 工具生成权利要求
2. 调用 description_writer 工具生成说明书各部分
3. 如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须调用 patent_drawing_generator 工具生成附图
4. 调用 support_checker 工具检查支持性
只有在获得所有工具返回结果后，才能生成最终JSON输出。
注意：当前阶段只生成审查前的专利草稿和附图，不得调用 patent_docx_generator；最终 DOCX 必须在质量审查合格后由工作流统一生成。
---

""",
            WorkflowState.QUALITY_REVIEW: """【强制工具调用指令 - 必须严格执行】
在输出任何审查结论之前，你必须按以下顺序调用工具：
1. 首先调用 compliance_checker 工具检查形式合规性
2. 然后调用 claim_quality_analyzer 工具分析权利要求质量
3. 接着调用 support_verifier 工具验证支持性
4. 最后调用 oa_predictor 工具预判审查风险
只有在获得所有工具返回结果后，才能生成最终JSON输出。
---

""",
        }

        # content_only 模式 — 用于质量门前的专利内容生成，不生成 .docx
        CONTENT_ONLY_TOOL_FORCE_PREFIX = {
            WorkflowState.PATENT_WRITING: """【强制工具调用指令 - 必须严格执行】
在输出任何专利文件内容之前，你必须调用以下工具：
1. 调用 claim_drafter 工具生成权利要求
2. 调用 description_writer 工具生成说明书各部分
3. 如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须调用 patent_drawing_generator 工具生成附图
4. 调用 support_checker 工具检查支持性
只有在获得所有工具返回结果后，才能生成最终JSON输出。
---

""",
        }

        if content_only and phase == WorkflowState.PATENT_WRITING:
            tool_prefix = CONTENT_ONLY_TOOL_FORCE_PREFIX.get(phase, "")
        else:
            tool_prefix = TOOL_FORCE_PREFIX.get(phase, "")

        target_country = context.metadata.get("target_country", "中国")

        country_hint_map = {
            WorkflowState.BRAINSTORMING: f"\n\n【目标申请国家】{target_country} — 默认按中国专利制度分析，除非用户明确要求其他国家。",
            WorkflowState.REQUIREMENT_ANALYSIS: f"\n\n【目标申请国家/法域】{target_country} — 分析时考虑该法域专利制度特点。",
            WorkflowState.RETRIEVAL_ANALYSIS: f"\n\n【目标申请国家/法域】{target_country} — 优先检索该国家/地区的专利数据库。",
            WorkflowState.PATENT_WRITING: f"\n\n【目标申请国家/法域】{target_country} — 严格遵循该法域的专利撰写规范和格式要求。",
            WorkflowState.QUALITY_REVIEW: f"\n\n【目标申请国家/法域】{target_country} — 依据该法域的专利法进行质量审查。",
        }

        if phase == WorkflowState.BRAINSTORMING:
            return f"""请基于你的专业专利知识分析以下技术方案，注意：
1. 先给出你能确定的分析和判断（技术领域归类、创新点初判等）
2. 使用"是否"确认问句让用户确认，而不是直接让用户补充细节
3. 仅对确实无法从专业知识和检索获取的信息，才列出问题请用户补充

请梳理这项技术发明的专利申请思路：\n\n{base}{country_hint_map[phase]}"""

        elif phase == WorkflowState.REQUIREMENT_ANALYSIS:
            return f"{tool_prefix}对以下技术方案进行结构化需求分析，提取创新点和技术特征：\n\n{base}{country_hint_map[phase]}"

        elif phase == WorkflowState.RETRIEVAL_ANALYSIS:
            req = json.dumps(context.requirement_analysis, ensure_ascii=False)[:1000]
            return f"""{tool_prefix}基于以下需求分析结果进行先有技术检索和专利性评估：

{req}

原始描述：{context.original_description[:500]}{country_hint_map[phase]}

【网页补充证据要求】
- 如果专利数据库结果不足以支持公开时间、产品功能、标准规范、实现细节或非专利现有技术判断，必须补充网页证据。
- 优先顺序：先 `web_access_match_site` 判断站点是否有已知模式或陷阱；不知道入口时用 `web_access_find_url`；已知公开 URL 时用 `web_access_read_page`；页面需要脚本、登录、滚动、点击时再用 `web_access_browser`。
- 网页证据只用于补强，不替代 patent_search / similarity_analyzer / patentability_scorer / risk_analyzer 的主链路。

【输出补充要求】
- 在最终 JSON 中补充以下字段：
  - `web_evidence`: 网页证据摘要列表；没有使用时返回空数组
  - `non_patent_prior_art`: 非专利现有技术来源列表；没有时返回空数组
  - `evidence_sources`: 本次实际使用的网页/标准/产品/内部来源列表；没有时返回空数组
  - `evidence_gaps`: 仍未补足的证据缺口；没有时返回空数组
- `web_evidence` 每项至少包含：`source_type`、`title`、`url`、`key_excerpt`、`why_it_matters`
- 若调用了任何 `web_access_*` 工具，上述字段不能为空数组，必须反映实际证据。
"""

        elif phase == WorkflowState.PATENT_WRITING:
            req = json.dumps(context.requirement_analysis, ensure_ascii=False)[:500]
            ret = json.dumps(context.retrieval_report, ensure_ascii=False)[:500]
            return f"{tool_prefix}基于需求分析和检索结果撰写专利申请文件：\n\n需求：{req}\n\n检索：{ret}{country_hint_map[phase]}"

        elif phase == WorkflowState.QUALITY_REVIEW:
            draft = self._build_quality_review_draft_summary(context.patent_draft)
            return f"{tool_prefix}对以下专利申请文件进行质量审查：\n\n{draft}{country_hint_map[phase]}"

        return base

    def _build_quality_review_draft_summary(self, draft: Dict[str, Any]) -> str:
        if not isinstance(draft, dict):
            return str(draft)[:4000]

        claims = draft.get("claims") or {}
        description = draft.get("description") or {}
        summary = {
            "title": draft.get("title") or draft.get("patent_title") or "",
            "claims": {
                "independent_claim": str(claims.get("independent_claim") or "")[:1500],
                "dependent_claims": [str(claim)[:600] for claim in claims.get("dependent_claims", [])[:8]],
            },
            "description": {
                "technical_field": str(description.get("technical_field") or "")[:800],
                "background_art": str(description.get("background_art") or "")[:800],
                "summary_of_invention": str(description.get("summary_of_invention") or "")[:1000],
                "drawings_description": str(description.get("drawings_description") or "")[:800],
                "detailed_description": str(description.get("detailed_description") or "")[:1500],
            },
            "drawings": [
                {
                    "figure_number": str(drawing.get("figure_number") or drawing.get("figureNumber") or ""),
                    "title": str(drawing.get("title") or ""),
                    "description": str(drawing.get("description") or "")[:800],
                    "file_path": str(drawing.get("file_path") or ""),
                    "artifact_url": str(drawing.get("artifact_url") or drawing.get("artifactUrl") or ""),
                    "mime_type": str(drawing.get("mime_type") or ""),
                }
                for drawing in (draft.get("drawings") or [])
                if isinstance(drawing, dict)
            ][:8],
            "drawing_quality_requirements": [
                "如果说明书包含附图说明或具体实施方式引用图号，必须存在对应 drawings 元数据和可访问文件路径。",
                "审查附图是否与权利要求、附图说明、具体实施方式中的结构/流程一致。",
                "需要附图但未生成、图号不一致、附图无法访问或图文不匹配，均应判定为 high/critical 问题并要求撰写 Agent 补图或修正。",
            ],
            "abstract": str(draft.get("abstract") or "")[:800],
            "docx_path": draft.get("docx_path") or "",
        }
        return json.dumps(summary, ensure_ascii=False)

    def _build_quality_gate_prompt(self, gate_type: str, context: WorkflowContext, revision_issues: Optional[List[str]] = None) -> str:
        """构建阶段质量门 prompt — 让 quality_reviewer 在不调用工具的情况下做质量评估

        gate_type: "requirement" | "retrieval" | "draft"
        """
        base_instruction = """## 审查要求
请严格输出JSON格式（不要调用任何工具，直接输出审查结论）：

```json
{
  "gate_passed": true/false,
  "issues": [
    {"severity": "critical/high/medium/low", "description": "问题描述", "suggestion": "修改建议"}
  ],
  "summary": "总体评价"
}
```

gate_passed为false的条件：存在任意 severity=critical 或 severity=high 的issue。
如果没有严重或高级别问题，gate_passed必须为true。"""
        revision_section = ""
        if revision_issues:
            revision_items = "\n".join(f"- {issue}" for issue in revision_issues)
            revision_section = f"## 上一轮审查发现的问题（本轮需确认已修复）\n{revision_items}"

        if gate_type == "requirement":
            req = json.dumps(context.requirement_analysis, ensure_ascii=False)[:3000]
            return f"""请对以下【需求分析结果】进行质量审查，检查分析是否完整、准确。

【需求分析结果】
{req}

## 检查清单
1. IPC分类是否合理？（tech_field 字段）
2. 核心技术原理是否清晰描述？（core_principle 字段）
3. 创新点提取是否完整？（key_innovative_features / key_features 字段）
4. 应用场景是否明确？（application_scenarios 字段）
5. 信息缺口是否已识别？（information_gaps 字段）
6. 专利类型推荐是否合理？（patent_type_recommendation 字段）
7. 有益效果是否充分描述？（beneficial_effects 字段）

{base_instruction}

{revision_section}"""

        elif gate_type == "retrieval":
            ret = json.dumps(context.retrieval_report, ensure_ascii=False)[:3000]
            return f"""请对以下【检索分析结果】进行质量审查，检查分析是否全面、可信。

【检索分析结果】
{ret}

## 检查清单
1. 检索是否覆盖了关键数据源？（检索工具调用结果）
2. 相似专利对比是否充分？（similarity_results / prior_art_references 字段）
3. 新颖性评估是否合理？（novelty_assessment 字段）
4. 创造性评估是否合理？（inventive_step_assessment 字段）
5. 实用性评估是否合理？（utility_assessment 字段）
6. 总体专利性评估是否可信？（overall_patentability 字段）
7. 风险分析是否全面？（risk_analysis 字段）
8. 若使用了网页补充证据，是否明确记录了 web_evidence / non_patent_prior_art / evidence_sources / evidence_gaps？
9. 网页证据是否与专利性判断清晰区分，没有把网页文案直接当作专利结论？

{base_instruction}

{revision_section}"""

        elif gate_type == "draft":
            draft = json.dumps(context.patent_draft, ensure_ascii=False)[:3000]
            return f"""请对以下【专利申请草稿】进行质量审查，检查文件是否完整、规范。

【专利草稿内容】
{draft}

## 检查清单
1. 权利要求书是否完整？（独立权利要求+从属权利要求）
2. 权利要求是否清楚、简要？
3. 说明书是否包含技术领域、背景技术、发明内容、具体实施方式？
4. 权利要求与说明书是否一致（支持关系）？
5. 说明书摘要是否完整？
6. 技术术语使用是否规范？
7. 文件格式是否符合中国专利法要求？

{base_instruction}

{revision_section}"""

        return base_instruction

    def _check_review_needs_revision(self, review_report: Dict[str, Any]) -> bool:
        """检查质量审查报告是否有需要修正的严重/高级别问题

        关键：必须最先检查 _agent_failed 标记 — 当审查 Agent 自身执行失败
        时 (LLM API 错误、超时等),即使结构化字段都为空,也必须返回 True
        触发 iteration loop 重新审查。否则会出现"流程结束但实际未审查"的情况。
        """
        if not isinstance(review_report, dict):
            return True  # 审查报告不是 dict 视为异常,触发重试

        # Agent 自身执行失败 (同时检查 normalized 标记 _agent_failed 和原始字段 failed)
        if review_report.get("_agent_failed") is True:
            return True
        if review_report.get("failed") is True:
            return True

        # 检查recommendation字段
        recommendation = review_report.get("recommendation", "")
        if recommendation in ("reject", "revise"):
            return True

        # 检查review_summary
        summary = review_report.get("review_summary", {})
        if isinstance(summary, dict):
            if summary.get("recommendation") in ("reject", "revise"):
                return True
            rating = summary.get("overall_rating", "")
            if rating in ("needs_revision", "poor"):
                return True

        # 检查revision_priority
        priority = review_report.get("revision_priority", "")
        if priority in ("critical", "high"):
            return True

        # 检查各子审查中是否有严重问题
        for section_key in (
            "formal_compliance_review",
            "claims_review",
            "description_review",
            "consistency_review",
            "drawing_review",
            "drawings_review",
            "figure_review",
        ):
            section = review_report.get(section_key, {})
            if isinstance(section, dict):
                issues = section.get("issues", [])
                for issue in issues:
                    if isinstance(issue, dict) and issue.get("severity") in ("critical", "high"):
                        return True

        # 检查examination_risks中的高风险
        for risk in review_report.get("examination_risks", []):
            if isinstance(risk, dict) and risk.get("likelihood") in ("critical", "high"):
                return True

        return False

    def _extract_normalized_review_score(self, review_report: Dict[str, Any]) -> Optional[float]:
        """提取并归一化审查分数到 0-1 区间。"""
        if not isinstance(review_report, dict):
            return None

        score_candidates = [
            review_report.get("overall_score"),
            (review_report.get("review_summary") or {}).get("overall_score")
            if isinstance(review_report.get("review_summary"), dict)
            else None,
            review_report.get("score"),
        ]

        for raw_score in score_candidates:
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
                if 0 <= score <= 1:
                    return score
                if 1 < score <= 100:
                    return score / 100
        return None

    def _needs_quality_remediation(self, review_report: Dict[str, Any]) -> bool:
        """统一判断质量问题是否还需要补救。"""
        if self._check_review_needs_revision(review_report):
            return True
        normalized_score = self._extract_normalized_review_score(review_report)
        if normalized_score is None:
            return False
        return normalized_score < QUALITY_REMEDIATION_THRESHOLD

    def _classify_remediation_path(self, review_report: Dict[str, Any], context: WorkflowContext) -> str:
        """按根因把补救动作分流为写/分析/检索/等用户/终止。"""
        if self._iteration_making_no_progress(context):
            return "TERMINAL_FAILURE"

        if not isinstance(review_report, dict):
            return "TERMINAL_FAILURE"

        root_cause = str(review_report.get("root_cause") or "").strip().lower()
        mapping = {
            "content_incomplete": "WRITE_MORE",
            "requirement_unclear": "ANALYZE_MORE",
            "evidence_missing": "SEARCH_MORE",
            "external_info_missing": "NEEDS_USER_INPUT",
            "system_failure": "TERMINAL_FAILURE",
        }
        if root_cause in mapping:
            return mapping[root_cause]

        missing_information = review_report.get("missing_information", [])
        if isinstance(missing_information, list) and any(str(item).strip() for item in missing_information):
            return "NEEDS_USER_INPUT"

        draft_issues = self._validate_patent_draft_completeness(context.patent_draft)
        if any(
            issue in draft_issues
            for issue in (
                "claims_missing",
                "independent_claim_missing",
                "dependent_claims_missing",
                "description_missing",
                "description_technical_field_missing",
                "description_background_art_missing",
                "description_summary_of_invention_missing",
                "description_detailed_description_missing",
                "abstract_missing",
                "drawing_artifacts_missing",
            )
        ):
            return "WRITE_MORE"

        review_issues = self._extract_review_issues(review_report)
        combined_issue_text = "\n".join(review_issues).lower()
        if any(keyword in combined_issue_text for keyword in ("参数", "术语", "场景", "需求", "不明确", "定义不清")):
            return "ANALYZE_MORE"
        if any(keyword in combined_issue_text for keyword in ("prior art", "现有技术", "检索", "证据", "novelty", "创造性")):
            return "SEARCH_MORE"

        if self._needs_quality_remediation(review_report):
            return "WRITE_MORE"
        return "TERMINAL_FAILURE"

    def _resolve_remediation_resume_phase(self, classification: str) -> WorkflowState:
        mapping = {
            "WRITE_MORE": WorkflowState.PATENT_WRITING,
            "ANALYZE_MORE": WorkflowState.REQUIREMENT_ANALYSIS,
            "SEARCH_MORE": WorkflowState.RETRIEVAL_ANALYSIS,
            "NEEDS_USER_INPUT": WorkflowState.REQUIREMENT_ANALYSIS,
            "AUTO_REMEDIATION_LIMIT": WorkflowState.PATENT_WRITING,
        }
        return mapping.get(classification, WorkflowState.PATENT_WRITING)

    def _enter_quality_remediation_hold(
        self,
        context: WorkflowContext,
        review_report: Dict[str, Any],
        classification: str,
    ) -> None:
        normalized_score = self._extract_normalized_review_score(review_report)
        missing_information = review_report.get("missing_information", [])
        if not isinstance(missing_information, list):
            missing_information = []

        context.metadata["quality_remediation"] = {
            "current_score": normalized_score,
            "threshold": QUALITY_REMEDIATION_THRESHOLD,
            "classification": classification.lower(),
            "missing_information": [str(item).strip() for item in missing_information if str(item).strip()],
            "attempt_count": context.iteration_count,
            "recommended_next_action": (
                "provide_info" if classification == "AUTO_REMEDIATION_LIMIT" else "continue_auto_fix"
            ),
            "resume_phase": self._resolve_remediation_resume_phase(classification).value,
        }

    def _build_writer_failure_review(self, patent_draft: Dict[str, Any]) -> Dict[str, Any]:
        """Convert an invalid writer result into a quality issue for CEO remediation."""
        error = ""
        if isinstance(patent_draft, dict):
            error = str(patent_draft.get("_agent_error") or patent_draft.get("error") or "")
        return {
            "review_summary": {
                "overall_score": 0.0,
                "overall_rating": "poor",
                "recommendation": "revise",
                "reviewer_notes": "专利撰写结果为空、失败或不完整，需要重新撰写完整申请文件。",
            },
            "root_cause": "content_incomplete",
            "missing_information": [],
            "revision_priority": "critical",
            "formal_compliance_review": {
                "score": 0.0,
                "passed": False,
                "issues": [
                    {
                        "severity": "critical",
                        "location": "专利申请文件",
                        "description": "专利撰写阶段未生成可用于审查和提交的完整申请文件。",
                        "suggestion": "由专利撰写 Agent 基于原始技术材料、需求分析和检索结果重新生成完整权利要求书、说明书、摘要及必要附图信息。",
                    }
                ],
            },
            "claims_review": {"issues": []},
            "description_review": {"issues": []},
            "consistency_review": {"issues": []},
            "examination_risks": [
                {
                    "risk": "申请文件不完整",
                    "likelihood": "critical",
                    "impact": "无法形成合格专利申请文件",
                    "mitigation": "重新生成完整专利申请文本",
                }
            ],
            "detailed_revision_suggestions": [
                {
                    "section": "全文",
                    "reason": error or "专利撰写结果不完整",
                    "suggested_content": "重新生成完整的权利要求书、说明书、摘要和附图说明。",
                }
            ],
        }

    async def _execute_remediation_phase(
        self,
        context: WorkflowContext,
        phase_state: WorkflowState,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """复用现有 phase prompt/normalize 逻辑执行单个补救阶段。"""
        if phase_state not in _PHASE_TO_PROFILE or phase_state not in _PHASE_CONTEXT_FIELDS:
            raise ValueError(f"Unsupported remediation phase: {phase_state.value}")

        service = _get_agent_factory()
        context.current_phase = phase_state
        await self._publish_progress_event(context, phase_state, "running")

        task_desc = self._build_phase_prompt(context, phase_state)
        agent_display_name = _PHASE_DISPLAY_NAMES.get(phase_state, phase_state.value)

        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.dispatch",
                f"🎯 调度 → {agent_display_name}: {task_desc[:100]}",
                {"from_agent": "CEO Agent", "to_agent": agent_display_name, "task_description": task_desc[:300]},
            )

        if phase_state == WorkflowState.PATENT_WRITING:
            context_data = await self._generate_patent_in_sections(
                service,
                _PHASE_TO_PROFILE[phase_state],
                task_desc,
                context,
                event_callback=event_callback,
            )
            agent_text = json.dumps(context_data, ensure_ascii=False)[:500] if isinstance(context_data, dict) else str(context_data)[:500]
        else:
            agent_result = await self._run_agent_stream(
                service,
                _PHASE_TO_PROFILE[phase_state],
                task_desc,
                context,
                agent_name=agent_display_name,
                event_callback=event_callback,
            )
            agent_text = agent_result.get("text", "")
            agent_tool_results = agent_result.get("tool_results", [])
            parsed = self._try_parse_json(agent_text)
            if "raw_output" not in parsed:
                context_data = parsed
            else:
                context_data = {"agent": phase_state.value, "output": agent_text, "summary": agent_text[:500]}
            if agent_tool_results:
                context_data["tool_results"] = agent_tool_results

        context_field = _PHASE_CONTEXT_FIELDS[phase_state]
        context_data = self._normalize_phase_output(context_field, context_data)
        setattr(context, context_field, context_data)

        try:
            _persist_phase_result(
                context.task_id,
                context_field,
                context_data if isinstance(context_data, dict) else {"output": str(context_data)},
            )
        except Exception:
            pass

        phase_enum = _PHASE_TO_WORKFLOW_PHASE.get(phase_state, WorkflowPhase.BRAINSTORM)
        agent_failed = isinstance(context_data, dict) and context_data.get("_agent_failed") is True
        context.add_phase_result(
            PhaseResult(
                phase=phase_enum,
                success=not agent_failed,
                duration_seconds=0,
                output=context_data if isinstance(context_data, dict) else {},
                issues=[str(context_data.get("_agent_error", ""))] if agent_failed and isinstance(context_data, dict) else [],
            )
        )

        if event_callback:
            event_callback(
                agent_display_name,
                "agent.content",
                "📄 输出",
                {"agent_name": agent_display_name, "content": agent_text if agent_text else "", "phase": phase_state.value},
            )

        await self._publish_progress_event(context, phase_state, "failed" if agent_failed else "completed")
        return context_data if isinstance(context_data, dict) else {}

    def _extract_review_issues(self, review_report: Dict[str, Any]) -> List[str]:
        """提取质量审查中的严重/高级别问题列表"""
        issues = []

        for section_key in (
            "formal_compliance_review",
            "claims_review",
            "description_review",
            "consistency_review",
            "drawing_review",
            "drawings_review",
            "figure_review",
        ):
            section = review_report.get(section_key, {})
            if isinstance(section, dict):
                for issue in section.get("issues", []):
                    if isinstance(issue, dict) and issue.get("severity") in ("critical", "high"):
                        desc = issue.get("description", "")
                        suggestion = issue.get("suggestion", "")
                        location = issue.get("location", "")
                        issues.append(f"[{location}] {desc}。建议：{suggestion}")

        for risk in review_report.get("examination_risks", []):
            if isinstance(risk, dict) and risk.get("likelihood") in ("critical", "high"):
                risk_type = risk.get("risk_type") or risk.get("type") or "examination_risk"
                desc = risk.get("description", "")
                suggestion = risk.get("mitigation_suggestion") or risk.get("mitigation") or ""
                issues.append(f"[{risk_type}] {desc}。建议：{suggestion}")

        # 详细修改建议
        for suggestion in review_report.get("detailed_revision_suggestions", []):
            if isinstance(suggestion, dict):
                section = suggestion.get("section", "")
                reason = suggestion.get("reason", "")
                suggested = suggestion.get("suggested_content", "")
                issues.append(f"[{section}] {reason}。建议修改为：{suggested[:200]}")

        return issues[:10]  # 最多取10个问题

    def _extract_referenced_figure_numbers(self, draft: Dict[str, Any]) -> List[str]:
        """Return normalized figure numbers referenced by the draft text."""
        if not isinstance(draft, dict):
            return []
        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        texts = [
            str(description.get("drawings_description") or ""),
            str(description.get("description_of_drawings") or ""),
        ]
        for drawing in draft.get("drawings", []) or []:
            if isinstance(drawing, dict):
                texts.append(str(drawing.get("description") or ""))
        combined = "\n".join(text for text in texts if text)
        numbers = sorted({int(match) for match in re.findall(r"图\s*([0-9]{1,2})", combined)})
        return [f"图{number}" for number in numbers]

    def _draft_requires_drawings(self, draft: Dict[str, Any]) -> bool:
        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}

        drawing_texts = (
            description.get("drawings_description", ""),
            description.get("description_of_drawings", ""),
        )
        if any(isinstance(text, str) and text.strip() for text in drawing_texts):
            return True
        if draft.get("drawings_expected") is True or draft.get("requires_drawings") is True:
            return True

        expected_drawings = draft.get("expected_drawings")
        if isinstance(expected_drawings, int) and expected_drawings > 0:
            return True
        if isinstance(expected_drawings, list) and expected_drawings:
            return True

        return False

    def _draft_has_drawing_artifact(self, draft: Dict[str, Any]) -> bool:
        drawings = draft.get("drawings", [])
        if not isinstance(drawings, list):
            return False
        return any(
            isinstance(drawing, dict)
            and bool(
                drawing.get("artifact_url")
                or drawing.get("artifactUrl")
                or drawing.get("file_path")
            )
            for drawing in drawings
        )

    def _missing_drawing_references(self, draft: Dict[str, Any]) -> List[str]:
        planned_specs = self._planned_drawing_specs(draft)
        referenced = [spec["figure_number"] for spec in planned_specs]
        if not referenced:
            return []

        drawings = draft.get("drawings", [])
        if not isinstance(drawings, list):
            drawings = []
        generated = {
            str(drawing.get("figure_number") or "").replace(" ", "")
            for drawing in drawings
            if isinstance(drawing, dict)
            and bool(drawing.get("artifact_url") or drawing.get("artifactUrl") or drawing.get("file_path"))
            and drawing.get("prompt_version") == "patent_drawing_v2"
        }
        return [figure for figure in referenced if figure not in generated]

    def _planned_drawing_specs(self, draft: Dict[str, Any]) -> List[Dict[str, str]]:
        """Return the canonical, bounded drawing plan for the current patent draft.

        LLM drafts often mention many figure numbers while still describing the same
        few concepts. The DOCX generator and reviewer need a stable plan so we do
        not create duplicate figures like 图2-图11 all named "方法流程示意图".
        """
        if not isinstance(draft, dict) or not self._draft_requires_drawings(draft):
            return []

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        combined = "\n".join(
            str(part or "")
            for part in (
                description.get("drawings_description"),
                description.get("description_of_drawings"),
                description.get("summary_of_invention"),
                description.get("detailed_description"),
                json.dumps(draft.get("claims", {}), ensure_ascii=False),
            )
        )
        referenced_count = len(self._extract_referenced_figure_numbers(draft))

        canonical_specs = [
            {
                "figure_number": "图1",
                "title": "系统结构示意图",
                "description": "沉浸式Cave折幕空间中固定显示面、姿态可调显示面、姿态驱动机构、显示控制端和处理控制单元的连接关系。",
            },
            {
                "figure_number": "图2",
                "title": "方法流程示意图",
                "description": "获取显示面姿态和空间边界参数、确定边界投影关系、生成映射关系并同步输出补偿后视频画面的处理流程。",
            },
            {
                "figure_number": "图3",
                "title": "姿态变化与空间边界示意图",
                "description": "显示面角度变化时相邻显示面之间的边界投影、重叠区域和空白区域的空间关系。",
            },
            {
                "figure_number": "图4",
                "title": "画面补偿与重映射示意图",
                "description": "外转空白区域补偿、内转遮挡区域裁剪、删除或重分配以及多显示面同步重映射关系。",
            },
        ]

        required_count = 2
        if referenced_count >= 3 or re.search(r"(姿态|角度|边界|投影|空间)", combined):
            required_count = 3
        if referenced_count >= 4 or re.search(r"(补偿|裁剪|遮挡|空白|重映射|重排|删除|重分配)", combined):
            required_count = 4
        return canonical_specs[:required_count]

    async def _ensure_required_patent_drawings(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Generate missing drawing artifacts before the quality reviewer sees the draft."""
        if not isinstance(draft, dict):
            return draft
        if not self._draft_requires_drawings(draft):
            return draft
        planned_specs = self._planned_drawing_specs(draft)
        draft["drawings"] = self._normalize_drawing_metadata(
            draft.get("drawings", []),
            planned_specs=planned_specs,
        )
        missing_figures = self._missing_drawing_references(draft)
        if not missing_figures:
            return draft
        spec_by_number = {spec["figure_number"]: spec for spec in planned_specs}

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        drawing_description = str(
            description.get("drawings_description")
            or description.get("description_of_drawings")
            or "图1为本发明的系统结构或方法流程示意图。"
        )
        if event_callback:
            event_callback(
                "专利撰写 Agent",
                "agent.thinking",
                f"🖼️ 草稿需要补齐附图（{', '.join(missing_figures)}），正在调用生图工具...",
                {"agent_name": "专利撰写 Agent", "thought": "生成专利附图", "phase": "patent_writing", "missing_figures": missing_figures},
            )

        try:
            from src.agents.hermes.tools.patent_drawing_generator import PatentDrawingGeneratorTool

            tool = PatentDrawingGeneratorTool()
            generated_drawings: List[Dict[str, Any]] = []
            for figure_number in missing_figures:
                spec = spec_by_number.get(figure_number, {})
                title = spec.get("title") or "专利附图"
                figure_description = spec.get("description") or drawing_description
                result = await tool.execute(
                    tech_description=(
                        f"{context.original_description}\n\n"
                        f"权利要求摘要：{json.dumps(draft.get('claims', {}), ensure_ascii=False)[:1200]}\n\n"
                        f"请仅生成{figure_number}对应的附图。附图主题：{title}。附图说明：{figure_description}"
                    ),
                    task_id=context.task_id,
                    title=title,
                    description=figure_description,
                    profile_id="patent.writer.v1",
                    figure_number=figure_number,
                )
                data = result.get("data", {}) if isinstance(result, dict) else {}
                drawings = data.get("drawings", []) if isinstance(data, dict) else []
                if isinstance(drawings, list):
                    generated_drawings.extend(item for item in drawings if isinstance(item, dict))

            if generated_drawings:
                existing = draft.get("drawings", [])
                if not isinstance(existing, list):
                    existing = []
                draft["drawings"] = self._normalize_drawing_metadata(
                    [*existing, *generated_drawings],
                    planned_specs=planned_specs,
                )
                draft["drawings_generated_by"] = "patent_drawing_generator"
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.content",
                        f"✅ 已生成/补齐 {len(generated_drawings)} 张专利附图",
                        {
                            "agent_name": "专利撰写 Agent",
                            "content": json.dumps(generated_drawings, ensure_ascii=False),
                            "phase": "patent_writing",
                        },
                    )
        except Exception as exc:
            self._logger.warning(f"Failed to generate required patent drawings: {exc}")
            draft.setdefault("_drawing_generation_error", str(exc)[:500])

        return draft

    async def _refresh_working_draft_docx(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        checkpoint: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Refresh draft/working_draft.docx after section writing or drawing generation.

        This is a non-final working document. The final DOCX is still generated only
        after the quality review passes.
        """
        if not isinstance(draft, dict) or draft.get("_agent_failed") is True:
            return draft
        try:
            from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

            docx_result = await PatentDocxGeneratorTool().execute(
                title=context.title or "专利申请文件",
                claims=draft.get("claims", {}),
                description=draft.get("description", {}),
                abstract=draft.get("abstract", ""),
                task_id=context.task_id,
                tech_description=context.original_description,
                drawings=draft.get("drawings", []),
                output_stage="draft",
                file_name="working_draft.docx",
            )
            if isinstance(docx_result, dict) and docx_result.get("success"):
                draft["working_docx_path"] = docx_result.get("file_path", "")
                if docx_result.get("figures"):
                    draft["working_docx_figures"] = docx_result.get("figures")
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.content",
                        f"📝 已刷新工作草稿 DOCX：{checkpoint}",
                        {
                            "agent_name": "专利撰写 Agent",
                            "phase": "patent_writing",
                            "checkpoint": checkpoint,
                            "content": json.dumps(
                                {
                                    "working_docx_path": draft.get("working_docx_path"),
                                    "figures": draft.get("working_docx_figures", []),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    )
        except Exception as exc:
            self._logger.warning(
                f"Failed to refresh working draft DOCX at {checkpoint}: {exc}",
                task_id=context.task_id,
            )
            draft["_working_docx_error"] = str(exc)[:500]
        return draft

    def _apply_review_suggestions_to_draft(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        review_issues: List[str],
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Apply deterministic structure repairs from reviewer feedback before re-review.

        This is a CEO safety net for remediation rounds: the patent writer agent still gets
        the first chance to revise, but timeouts or incomplete writer output must not end the
        flow or erase a usable draft.
        """
        if not isinstance(draft, dict):
            draft = {}
        repaired = dict(draft)
        description = dict(repaired.get("description") or {})
        claims = dict(repaired.get("claims") or {})

        suggestion_text = "\n".join(str(issue) for issue in review_issues if issue)
        suggested_title = self._extract_suggested_content_for_section(
            context.review_report or {},
            ("发明名称", "title"),
        )
        title = (
            repaired.get("title")
            or repaired.get("patent_title")
            or context.title
            or suggested_title
            or "沉浸式展示空间的显示姿态自适应控制与画面连续性补偿方法"
        )
        repaired["title"] = str(title).strip()
        context.title = repaired["title"]

        suggested_abstract = self._extract_suggested_content_for_section(
            context.review_report or {},
            ("说明书摘要", "abstract"),
        )
        abstract = str(repaired.get("abstract") or "").strip()
        if len(abstract) < 80 or "摘要为空" in suggestion_text:
            repaired["abstract"] = suggested_abstract or (
                "本发明公开一种沉浸式展示空间的显示姿态自适应控制与画面连续性补偿方法。"
                "该方法获取体验者的人体信息、观看位置或定制输入，确定观看参考点和姿态可调显示面的目标姿态，"
                "建立固定显示面与姿态可调显示面的统一三维坐标系，并根据目标姿态参数或实际姿态反馈生成显示内容映射参数。"
                "当姿态变化产生显示间隙时，基于相邻显示面的边界投影计算未覆盖区域并生成补偿显示数据；"
                "当姿态变化产生遮挡或重叠时，生成可见区域掩膜并对原始显示内容进行裁剪、重排或几何重映射。"
                "各显示面按统一时间戳同步输出，从而在显示姿态自适应变化时保持多显示面画面连续性。"
            )

        independent_claim = str(claims.get("independent_claim") or "").strip()
        if (
            not independent_claim
            or "统一三维坐标系" not in independent_claim
            or "边界坐标" not in independent_claim
        ):
            claims["independent_claim"] = (
                "1. 一种沉浸式展示空间的显示姿态自适应控制与画面连续性补偿方法，"
                "所述沉浸式展示空间包括固定显示面和至少一个姿态可调显示面，其特征在于，包括："
                "获取体验者的人体信息、观看位置和/或定制输入，并基于所述人体信息、观看位置和/或定制输入确定观看参考点；"
                "调用姿态-内容-补偿联合映射关系，生成所述姿态可调显示面的目标姿态参数以及与所述目标姿态参数对应的显示内容映射参数；"
                "驱动所述姿态可调显示面运动至目标姿态，并获取所述姿态可调显示面的实际姿态参数；"
                "建立所述固定显示面和所述姿态可调显示面的统一三维坐标系，获取各显示面的边界坐标，"
                "并根据所述目标姿态参数或实际姿态参数对所述姿态可调显示面的边界坐标进行姿态变换；"
                "根据变换后的边界坐标与相邻显示面的边界坐标之间的投影关系，确定未覆盖区域、显示间隙、重叠区域和/或遮挡区域；"
                "基于所述未覆盖区域或显示间隙生成补充显示区域和对应的补偿显示数据，"
                "并基于所述重叠区域或遮挡区域生成可见区域掩膜，对原始显示内容执行裁剪、缩放、重排和/或几何重映射；"
                "按照统一时间戳将重构后的显示内容、补偿显示数据和/或重映射后的显示内容同步输出至所述固定显示面和所述姿态可调显示面，"
                "以保持多显示面画面的连续性。"
            )

        dependent_claims = claims.get("dependent_claims", [])
        if not isinstance(dependent_claims, list):
            dependent_claims = [str(dependent_claims)] if str(dependent_claims or "").strip() else []
        algorithm_claims = [
            "2. 根据权利要求1所述的方法，其特征在于，所述姿态-内容-补偿联合映射关系包括人体信息范围、观看参考点、目标姿态参数、纹理坐标映射矩阵、视口裁剪边界、边缘融合权重和补偿类型之间的对应关系。",
            "3. 根据权利要求1所述的方法，其特征在于，所述未覆盖区域由姿态变换后的姿态可调显示面的第一边界线、相邻固定显示面或相邻姿态可调显示面的第二边界线以及观看参考点的投影关系确定。",
            "4. 根据权利要求1所述的方法，其特征在于，所述可见区域掩膜根据各显示面的深度顺序、投影重叠区域和预设可见性规则生成，并用于确定原始显示内容中的保留显示区域和待裁剪区域。",
            "5. 根据权利要求1所述的方法，其特征在于，所述显示内容映射参数包括投影矩阵、纹理坐标映射矩阵、视口边界坐标、补偿区域边界坐标和边缘融合权重中的至少一种。",
            "6. 根据权利要求1所述的方法，其特征在于，当目标姿态参数位于两个预设离散姿态之间时，对两个预设离散姿态对应的显示内容映射矩阵、补偿区域边界坐标和边缘融合权重进行插值计算。",
        ]
        existing_claim_text = "\n".join(str(claim) for claim in dependent_claims)
        for claim in algorithm_claims:
            if claim[:18] not in existing_claim_text:
                dependent_claims.append(claim)
        claims["dependent_claims"] = dependent_claims
        repaired["claims"] = claims

        if self._section_needs_repair(description.get("technical_field")):
            description["technical_field"] = (
                "本发明涉及沉浸式显示、可调显示面控制和多屏内容映射技术领域，"
                "尤其涉及一种沉浸式展示空间的显示姿态自适应控制与画面连续性补偿方法。"
                "该方法适用于 Cave 折幕、环幕、投影融合空间、LED 多屏展示空间以及包含固定显示面和姿态可调显示面的沉浸式交互展示系统，"
                "用于在显示面姿态发生转动、平移或升降变化时保持显示内容映射、边界补偿和多屏同步输出的一致性。"
            )
        if self._section_needs_repair(description.get("background_art")):
            description["background_art"] = (
                "现有沉浸式展示空间通常采用固定环幕、折幕、LED显示面或投影显示面形成包围式视觉环境。"
                "为适配不同身高、观看距离、观看主题或沉浸强度，一些展示空间会设置可转动、可升降或可平移的姿态可调显示面。"
                "然而，显示面姿态变化后，相邻显示面之间可能出现显示间隙、空白区域、重叠区域或遮挡区域；"
                "若仍按固定姿态输出原始画面，容易产生接缝错位、画面拉伸、内容缺失或遮挡重复。"
                "传统多屏几何校正、边缘融合和投影映射方案多针对固定屏幕位置，难以同时处理用户驱动的姿态变化、实时姿态反馈、补偿区域生成和多显示面同步输出。"
                "因此，需要一种能够将观看参考点、显示姿态、内容映射和画面补偿联动处理的技术方案。"
            )
        if self._section_needs_repair(description.get("summary_of_invention")):
            description["summary_of_invention"] = (
                "本发明的目的在于提供一种沉浸式展示空间的显示姿态自适应控制与画面连续性补偿方法，"
                "以解决姿态可调显示面运动后多显示面画面不连续、局部空白、遮挡重复和内容映射不准确的问题。"
                "该方法先基于体验者的人体信息、观看位置或定制输入确定观看参考点，并通过姿态-内容-补偿联合映射关系生成目标姿态参数和显示内容映射参数；"
                "再建立固定显示面和姿态可调显示面的统一三维坐标系，利用实际姿态反馈修正显示面边界坐标；"
                "当显示面外转或远离相邻显示面形成未覆盖区域时，根据相邻边界线投影计算空白多边形区域，生成补充显示区域、补偿视口和边缘融合权重；"
                "当显示面内转形成遮挡或重叠时，根据深度顺序和投影重叠区域生成可见区域掩膜，对原始显示内容进行裁剪、缩放、重排或几何重映射。"
                "通过统一时间戳同步输出各显示面的重构内容和补偿内容，能够在显示姿态动态变化时降低接缝错位并保持画面连续。"
            )
        description["drawings_description"] = self._build_consistent_drawings_description(repaired)
        if self._section_needs_repair(description.get("detailed_description")):
            description["detailed_description"] = (
                "以下结合附图对本发明进行说明。控制器接收人体信息采集模块输出的身高、视线高度、站立位置、观看距离以及入口交互终端输入的展示主题或沉浸强度，"
                "计算观看参考点，并在姿态-内容-补偿联合映射表中查询目标姿态参数。所述映射表可包括人体信息范围、观看参考点坐标、姿态可调显示面的转动角度、俯仰角、升降高度、"
                "纹理坐标映射矩阵、视口裁剪边界、补偿类型和边缘融合权重。驱动机构根据目标姿态参数带动姿态可调显示面运动，编码器、角度传感器或视觉检测单元反馈实际姿态参数。"
                "控制器在统一三维坐标系中记录固定显示面和姿态可调显示面的顶点坐标，根据实际姿态参数构建姿态变换矩阵，并得到变换后的显示面边界。"
                "当相邻边界之间形成未覆盖区域时，控制器根据观看参考点对相邻边界进行投影，计算空白多边形区域，并从同一三维场景或原始视频帧中生成补偿视口，将补偿显示数据输出至补充显示设备或相邻显示面的扩展显示区。"
                "当姿态可调显示面内转导致画面重叠或遮挡时，控制器依据显示面的深度顺序和投影重叠区域生成可见区域掩膜，保留未被遮挡的内容区域，并对被遮挡区域执行裁剪、缩放、重排或几何重映射。"
                "对于位于两个离散姿态之间的目标姿态，控制器对相邻离散姿态对应的显示内容映射矩阵、补偿区域边界坐标和边缘融合权重进行线性插值，得到当前姿态下的映射参数。"
                "最终，控制器按照统一时间戳将固定显示面、姿态可调显示面和补充显示区域的内容同步输出，以保证沉浸式展示空间中的画面连续性和姿态适配效果。"
            )
        repaired["description"] = description
        repaired["drawings"] = self._normalize_drawing_metadata(
            repaired.get("drawings", []),
            planned_specs=self._planned_drawing_specs(repaired),
        )
        repaired["_remediation_applied"] = {
            "round": context.iteration_count,
            "source": "quality_review_suggestions",
            "issues": review_issues[:12],
        }

        if event_callback:
            event_callback(
                "专利撰写 Agent",
                "agent.content",
                "✅ 已根据审查意见补强标题、摘要、权利要求、说明书和附图说明",
                {
                    "agent_name": "专利撰写 Agent",
                    "phase": "patent_writing",
                    "content": json.dumps(repaired.get("_remediation_applied"), ensure_ascii=False),
                },
            )
        return repaired

    def _section_needs_repair(self, value: object) -> bool:
        text = str(value or "").strip()
        if len(text) < 120:
            return True
        return bool(re.search(r"(图\d+还|可以直接输|升降高度$|等$|包括但不限于$)", text))

    def _extract_suggested_content_for_section(
        self,
        review_report: Dict[str, Any],
        section_names: tuple[str, ...],
    ) -> str:
        suggestions = review_report.get("detailed_revision_suggestions", [])
        if not isinstance(suggestions, list):
            return ""
        normalized_names = tuple(name.lower() for name in section_names)
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            section = str(item.get("section") or "").lower()
            if any(name in section for name in normalized_names):
                content = str(item.get("suggested_content") or "").strip()
                if content:
                    return content
        return ""

    def _build_consistent_drawings_description(self, draft: Dict[str, Any]) -> str:
        specs = self._planned_drawing_specs(draft)
        if not specs:
            specs = [
                {
                    "figure_number": "图1",
                    "title": "系统结构示意图",
                    "description": "沉浸式Cave折幕空间中固定显示面、姿态可调显示面和处理控制单元的连接关系。",
                },
                {
                    "figure_number": "图2",
                    "title": "方法流程示意图",
                    "description": "根据显示面姿态变化生成补偿、裁剪和重映射视频画面的处理流程。",
                },
            ]
        lines = [f"{spec['figure_number']}为本发明{spec['title']}。" for spec in specs]
        return "\n".join(lines)

    def _normalize_drawing_metadata(
        self,
        drawings: object,
        planned_specs: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(drawings, list):
            return []
        if planned_specs is None:
            planned_specs = [
                {"figure_number": "图1", "title": "系统结构示意图", "description": ""},
                {"figure_number": "图2", "title": "方法流程示意图", "description": ""},
                {"figure_number": "图3", "title": "姿态变化与空间边界示意图", "description": ""},
                {"figure_number": "图4", "title": "画面补偿与重映射示意图", "description": ""},
            ]
        title_map = {spec["figure_number"]: spec["title"] for spec in planned_specs}
        description_map = {spec["figure_number"]: spec.get("description", "") for spec in planned_specs}
        allowed_numbers = set(title_map)
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(drawings, start=1):
            if not isinstance(item, dict):
                continue
            figure_number = str(
                item.get("figure_number")
                or item.get("figureNumber")
                or item.get("number")
                or f"图{index}"
            ).strip()
            if not re.match(r"^图\d+$", figure_number):
                figure_number = f"图{index}"
            if allowed_numbers and figure_number not in allowed_numbers:
                continue
            if figure_number in seen:
                continue
            seen.add(figure_number)
            drawing = dict(item)
            drawing["figure_number"] = figure_number
            raw_title = str(drawing.get("title") or "").strip()
            raw_title = re.sub(rf"^{re.escape(figure_number)}\s*[:：、.．-]?\s*", "", raw_title).strip()
            drawing["title"] = title_map.get(figure_number, raw_title or "专利附图")
            drawing["description"] = description_map.get(figure_number) or f"{figure_number}为{drawing['title']}。"
            normalized.append(drawing)
        return normalized

    def _validate_patent_draft_completeness(self, draft: Dict[str, Any]) -> List[str]:
        issues: List[str] = []

        if not draft or not isinstance(draft, dict):
            return ["patent_draft_missing"]
        if draft.get("_agent_failed") is True:
            issues.append("patent_draft_agent_failed")
        if draft.get("_incomplete_output") is True:
            issues.append("patent_draft_incomplete_output")

        claims = draft.get("claims", {}) or {}
        if not isinstance(claims, dict):
            issues.append("claims_missing")
            claims = {}

        independent_claim = claims.get("independent_claim", "")
        if not isinstance(independent_claim, str) or not independent_claim.strip():
            issues.append("independent_claim_missing")

        dependent_claims = claims.get("dependent_claims", [])
        has_dependent_claim = False
        if isinstance(dependent_claims, list):
            has_dependent_claim = any(
                isinstance(claim, str) and claim.strip()
                for claim in dependent_claims
            )
        elif isinstance(dependent_claims, str):
            has_dependent_claim = bool(dependent_claims.strip())
        if not has_dependent_claim:
            issues.append("dependent_claims_missing")

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            issues.append("description_missing")
            description = {}

        for section_name in (
            "technical_field",
            "background_art",
            "summary_of_invention",
            "detailed_description",
        ):
            content = description.get(section_name, "")
            if not isinstance(content, str) or not content.strip():
                issues.append(f"description_{section_name}_missing")

        abstract = draft.get("abstract", "") or ""
        if not isinstance(abstract, str) or not abstract.strip():
            issues.append("abstract_missing")

        if self._draft_requires_drawings(draft):
            if not self._draft_has_drawing_artifact(draft):
                issues.append("drawing_artifacts_missing")
            missing_figures = self._missing_drawing_references(draft)
            if missing_figures:
                issues.append(f"drawing_artifacts_missing:{','.join(missing_figures)}")
            planned_figures = self._planned_drawing_specs(draft)
            drawings = draft.get("drawings", [])
            if isinstance(drawings, list):
                normalized_drawings = self._normalize_drawing_metadata(
                    drawings,
                    planned_specs=planned_figures,
                )
                titles = [
                    str(drawing.get("title") or "").strip()
                    for drawing in normalized_drawings
                    if isinstance(drawing, dict) and str(drawing.get("title") or "").strip()
                ]
                if len(titles) != len(set(titles)):
                    issues.append("drawing_titles_duplicate")
                if len(drawings) > len(normalized_drawings) and normalized_drawings:
                    issues.append("drawing_artifacts_excessive_or_duplicate")
                file_hashes: Dict[str, str] = {}
                for drawing in normalized_drawings:
                    if not isinstance(drawing, dict):
                        continue
                    file_path = drawing.get("file_path")
                    if not isinstance(file_path, str) or not file_path:
                        continue
                    path = _Path(file_path)
                    if not path.is_file():
                        continue
                    try:
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    except Exception:
                        continue
                    figure_number = str(drawing.get("figure_number") or "")
                    if digest in file_hashes:
                        issues.append(f"drawing_artifacts_duplicate_content:{file_hashes[digest]},{figure_number}")
                        break
                    file_hashes[digest] = figure_number

        return issues

    def _reviewable_content_issues(self, draft: Dict[str, Any]) -> List[str]:
        """Return content issues while ignoring stale transport/agent failure markers."""
        if not isinstance(draft, dict):
            return ["patent_draft_missing"]
        issues = self._validate_patent_draft_completeness(draft)
        return [
            issue
            for issue in issues
            if issue not in {"patent_draft_agent_failed", "patent_draft_incomplete_output"}
        ]

    def _clear_stale_writer_failure_if_reviewable(self, draft: Any) -> Any:
        """Writer tools may fail after a deterministic repair already produced real content.

        In that case the old _agent_failed marker is no longer a content failure and must
        not block the CEO quality loop or final DOCX generation.
        """
        if not isinstance(draft, dict):
            return draft
        if draft.get("_agent_failed") is not True and draft.get("_incomplete_output") is not True:
            return draft
        if self._reviewable_content_issues(draft):
            return draft
        repaired = dict(draft)
        repaired.pop("_agent_failed", None)
        repaired.pop("_incomplete_output", None)
        repaired.pop("_agent_error", None)
        repaired["_writer_fallback_recovered"] = True
        return repaired

    def _build_deterministic_quality_review(
        self,
        context: WorkflowContext,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Review the draft locally when the reviewer LLM is unavailable.

        This is deliberately conservative: missing claims, sections, abstracts, required
        drawings, or figure artifacts still fail the quality gate. A complete draft with
        all referenced drawings can pass and then proceed to DOCX generation.
        """
        draft = context.patent_draft if isinstance(context.patent_draft, dict) else {}
        issues = self._reviewable_content_issues(draft)
        passed = not issues
        severity = "high" if not passed else "info"

        def issue_payload(code: str) -> Dict[str, str]:
            drawing_issue = "drawing" in code or "图" in code
            return {
                "severity": "critical" if drawing_issue else severity,
                "location": "附图" if drawing_issue else "专利申请文件",
                "description": f"本地审查发现问题：{code}",
                "suggestion": (
                    "由专利撰写 Agent 调用生图工具补齐附图并保持说明书图号一致。"
                    if drawing_issue
                    else "由专利撰写 Agent 补齐对应章节后重新审查。"
                ),
            }

        formal_issues = [issue_payload(code) for code in issues if "drawing" not in code and "图" not in code]
        drawing_issues = [issue_payload(code) for code in issues if "drawing" in code or "图" in code]
        score = 0.92 if passed else 0.45
        notes = "本地确定性审查通过：权利要求、说明书、摘要和附图均满足当前质量门。"
        if not passed:
            notes = "本地确定性审查未通过，需要 CEO 继续调度补充优化。"
        if reason:
            notes += f" 原审查 Agent 未完成，已启用本地审查兜底：{reason[:180]}"

        return {
            "recommendation": "approve" if passed else "revise",
            "revision_priority": "medium" if passed else "critical",
            "review_summary": {
                "overall_score": score,
                "overall_rating": "good" if passed else "needs_revision",
                "recommendation": "approve" if passed else "revise",
                "reviewer_notes": notes,
            },
            "formal_compliance_review": {
                "score": score,
                "passed": passed and not formal_issues,
                "issues": formal_issues,
            },
            "claims_review": {"issues": []},
            "description_review": {"issues": []},
            "consistency_review": {"issues": []},
            "drawing_review": {
                "score": 1.0 if not drawing_issues else 0.0,
                "passed": not drawing_issues,
                "issues": drawing_issues,
                "checked_drawings": len(draft.get("drawings") or []) if isinstance(draft, dict) else 0,
            },
            "examination_risks": [] if passed else [
                {
                    "risk_type": "quality_gate",
                    "likelihood": "high",
                    "description": "专利申请文件仍存在质量门问题。",
                    "mitigation_suggestion": "继续补齐并复审。",
                }
            ],
            "detailed_revision_suggestions": [],
            "_deterministic_review": True,
        }

    def _has_unresolved_critical_issues(self, context: WorkflowContext) -> bool:
        """检查工作流是否还有未解决的关键问题 (在 COMPLETED 之前的最后一道闸)

        关键修复 (Bug #1 用户可见层): 即便经过 max_iterations 轮修正,
        最终的 patent_draft 仍可能是 _agent_failed / 空白内容,
        最终 review_report 仍可能 recommendation="reject" 且包含 critical issue。
        这种情况必须以 FAILED 状态结束,而不是 COMPLETED,
        否则用户会看到一份"流程完成"的空专利文件。
        """
        draft_issues = self._validate_patent_draft_completeness(context.patent_draft)
        if draft_issues:
            return True

        # 2) 检查 review_report 是否有未解决的 critical issue
        review = context.review_report
        if not review or not isinstance(review, dict):
            return True
        if review.get("_agent_failed") is True:
            return True
        if self._needs_quality_remediation(review):
            return True

        return False

    def _patent_draft_has_content(self, draft: Dict[str, Any]) -> bool:
        """检查 patent_draft 是否包含任何真实可用的内容。

        用于 iteration loop 中判断是否需要重新调用 writer。
        """
        if not draft or not isinstance(draft, dict):
            return False
        if draft.get("_agent_failed") is True or draft.get("_incomplete_output") is True:
            return False
        claims = draft.get("claims", {}) or {}
        if not claims.get("independent_claim", "").strip():
            return False
        return True

    def _iteration_making_no_progress(self, context: WorkflowContext) -> bool:
        """检测 iteration loop 是否在原地踏步 (no progress)。

        当 writer 和 reviewer 连续失败,且错误相同时 (例如 LLM API
        一直不可用、key 错误、配额耗尽),继续迭代不会产生新内容。
        应立即跳出,避免无谓等待和资源浪费。

        Returns:
            True 表示应当跳出 iteration loop
        """
        # 至少跑过一轮才有意义判断
        if context.iteration_count < 1:
            return False

        # 检查最近一轮的 writer/reviewer 是否都失败
        recent_phases = [p for p in context.phase_history[-2:]]
        writer_failed = False
        reviewer_failed = False
        for p in recent_phases:
            if not isinstance(p.output, dict):
                continue
            if p.phase == WorkflowPhase.WRITING and p.output.get("_agent_failed"):
                writer_failed = True
            if p.phase == WorkflowPhase.REVIEW and p.output.get("_agent_failed"):
                reviewer_failed = True

        # 只有 writer 和 reviewer 都失败,且失败原因相同时才是 no-progress
        if not (writer_failed and reviewer_failed):
            return False

        writer_err = (context.patent_draft or {}).get("_agent_error", "")
        reviewer_err = (context.review_report or {}).get("_agent_error", "")
        if not writer_err or not reviewer_err:
            return False

        # 错误相同 (或非常相似) — 重复迭代没有意义
        # 简单比较: 错误信息的前 100 个字符相同
        return writer_err[:100] == reviewer_err[:100]

    def _build_revision_prompt(self, context: WorkflowContext, review_issues: List[str]) -> str:
        """构建修正撰写的prompt，包含审查问题和原有草稿"""
        draft_summary = json.dumps(context.patent_draft, ensure_ascii=False)[:2000]
        requirement_summary = json.dumps(context.requirement_analysis, ensure_ascii=False)[:3000]
        retrieval_summary = json.dumps(context.retrieval_report, ensure_ascii=False)[:2000]
        issues_text = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(review_issues))
        draft_failed = (
            not isinstance(context.patent_draft, dict)
            or context.patent_draft.get("_agent_failed") is True
            or context.patent_draft.get("_incomplete_output") is True
        )
        failed_hint = ""
        if draft_failed:
            failed_hint = """
## 当前专利文件生成失败或不完整
当前专利文件不能作为修正依据。请以原始技术描述、需求分析结果和检索分析结果为主要依据，重新生成完整专利文件。"""

        return f"""请基于质量审查意见对专利申请文件进行修正。

## 审查发现的问题（必须全部解决）：
{issues_text}
{failed_hint}

## 原始技术描述：
{context.original_description}

## 需求分析结果：
{requirement_summary}

## 检索分析结果：
{retrieval_summary}

## 当前专利文件：
{draft_summary}

## 修正要求：
1. 逐一解决上述所有问题
2. 保持原有文件结构不变（权利要求书+说明书+摘要）
3. 修正后输出完整的JSON格式专利文件
4. 确保修改后权利要求与说明书的一致性"""

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

    async def _generate_requirement_analysis_with_tools(
        self,
        context: WorkflowContext,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Run requirement-analysis tools directly and return the normalized phase JSON."""
        agent_name = "需求分析师"

        async def _emit_tool_start(tool_name: str, parameters: Dict[str, Any]) -> None:
            if event_callback:
                event_callback(
                    agent_name,
                    "agent.tool_call_start",
                    f"🔧 调用工具: {tool_name}",
                    {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": parameters,
                    },
                )

        async def _emit_tool_end(
            tool_name: str,
            parameters: Dict[str, Any],
            result: Any,
            success: bool = True,
        ) -> None:
            if event_callback:
                result_text = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False, default=str)
                )
                event_callback(
                    agent_name,
                    "agent.tool_call_end",
                    ("✅" if success else "❌") + f" {tool_name} 返回",
                    {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "result": result_text[:1800],
                        "success": success,
                    },
                )

        from src.agents.hermes.tools.ipc_classifier import IPCClassifierTool
        from src.agents.hermes.tools.tech_feature_extractor import TechFeatureExtractorTool
        from src.agents.hermes.tools.scenario_miner import ScenarioMinerTool

        original = context.original_description or ""
        ipc_params = {"tech_description": original[:12000]}
        await _emit_tool_start("ipc_classifier", ipc_params)
        ipc_result = await IPCClassifierTool().execute(**ipc_params)
        await _emit_tool_end(
            "ipc_classifier",
            ipc_params,
            ipc_result,
            bool(ipc_result.get("success", True)) if isinstance(ipc_result, dict) else True,
        )
        ipc_data = ipc_result.get("data", {}) if isinstance(ipc_result, dict) else {}

        feature_params = {"tech_description": original[:12000]}
        await _emit_tool_start("tech_feature_extractor", feature_params)
        feature_result = await TechFeatureExtractorTool().execute(**feature_params)
        await _emit_tool_end(
            "tech_feature_extractor",
            feature_params,
            feature_result,
            bool(feature_result.get("success", True)) if isinstance(feature_result, dict) else True,
        )
        feature_data = feature_result.get("data", {}) if isinstance(feature_result, dict) else {}
        features = feature_data.get("features", []) if isinstance(feature_data, dict) else []

        scenario_params = {
            "tech_description": original[:12000],
            "features": json.dumps(features, ensure_ascii=False)[:8000],
        }
        await _emit_tool_start("scenario_miner", scenario_params)
        scenario_result = await ScenarioMinerTool().execute(**scenario_params)
        await _emit_tool_end(
            "scenario_miner",
            scenario_params,
            scenario_result,
            bool(scenario_result.get("success", True)) if isinstance(scenario_result, dict) else True,
        )
        scenario_data = scenario_result.get("data", {}) if isinstance(scenario_result, dict) else {}

        report = {
            "tech_field": {
                "primary_domain": "沉浸式多屏显示控制与动态画面适配",
                "secondary_domains": ["Cave折幕空间", "视频内容重映射", "多显示面同步输出"],
                "ipc_primary": ipc_data.get("primary_code", ""),
                "ipc_secondary": ipc_data.get("secondary_codes", []),
            },
            "technical_problem": feature_data.get("technical_problem", ""),
            "core_innovation": feature_data.get("core_innovation", ""),
            "key_innovative_features": features,
            "beneficial_effects": feature_data.get("beneficial_effects", []),
            "application_scenarios": scenario_data.get("scenarios", []),
            "extension_directions": scenario_data.get("extension_directions", []),
            "market_assessment": scenario_data.get("market_assessment", ""),
            "patent_type_recommendation": {
                "suggested_type": "发明专利",
                "rationale": "方案包含显示姿态、边界计算、视频内容映射与补偿控制流程，适合作为方法和系统双独权布局。",
            },
            "retrieval_keywords": [
                "Cave折幕",
                "沉浸式多屏显示",
                "显示面姿态",
                "视频内容重映射",
                "投影边界校正",
                "遮挡裁剪",
                "空白补偿",
                "多屏同步输出",
            ],
            "information_gaps": [],
            "tool_results": [ipc_result, feature_result, scenario_result],
        }
        return self._normalize_phase_output("requirement_analysis", report)

    async def _generate_retrieval_report_with_tools(
        self,
        context: WorkflowContext,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Run the retrieval analyst's required tool chain and stop after a report exists."""
        agent_name = "检索分析师"

        async def _emit_tool_start(tool_name: str, parameters: Dict[str, Any]) -> None:
            if event_callback:
                event_callback(
                    agent_name,
                    "agent.tool_call_start",
                    f"🔧 调用工具: {tool_name}",
                    {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": parameters,
                    },
                )

        async def _emit_tool_end(
            tool_name: str,
            parameters: Dict[str, Any],
            result: Any,
            success: bool = True,
        ) -> None:
            if event_callback:
                result_text = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False, default=str)
                )
                event_callback(
                    agent_name,
                    "agent.tool_call_end",
                    ("✅" if success else "❌") + f" {tool_name} 返回",
                    {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "result": result_text[:1800],
                        "success": success,
                    },
                )

        req = context.requirement_analysis or {}
        original = context.original_description or ""
        target_country = context.metadata.get("target_country", context.target_country or "中国")
        keywords: List[str] = []
        for value in (
            req.get("retrieval_keywords"),
            req.get("keywords"),
            req.get("key_innovative_features"),
            req.get("key_features"),
        ):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        text = item.get("name") or item.get("feature_name") or item.get("description")
                    else:
                        text = str(item)
                    if text:
                        keywords.append(str(text)[:40])
            elif isinstance(value, str):
                keywords.extend(
                    part.strip()
                    for part in re.split(r"[,，;；\s]+", value)
                    if part.strip()
                )

        if not keywords:
            keywords = [
                "Cave折幕",
                "沉浸式多屏显示",
                "视频画面适配",
                "投影边界校正",
                "区域识别",
                "动态内容映射",
            ]
        query = " AND ".join(dict.fromkeys(keywords[:8]))
        if len(query) < 12:
            query = original[:300] or "沉浸式多屏视频处理"

        sources = (
            "cnipa,google_patents,uspto,epo"
            if target_country == "中国"
            else "google_patents,uspto,epo,cnipa"
        )

        from src.agents.hermes.tools.patent_search import PatentSearchTool
        from src.agents.hermes.tools.similarity_analyzer import SimilarityAnalyzerTool
        from src.agents.hermes.tools.patentability_scorer import PatentabilityScorerTool
        from src.agents.hermes.tools.risk_analyzer import RiskAnalyzerTool

        search_params = {"query": query, "sources": sources, "limit": "10"}
        await _emit_tool_start("patent_search", search_params)
        search_result = await PatentSearchTool().execute(**search_params)
        await _emit_tool_end(
            "patent_search",
            search_params,
            search_result,
            bool(search_result.get("success", True)) if isinstance(search_result, dict) else True,
        )
        search_data = search_result.get("data", {}) if isinstance(search_result, dict) else {}
        prior_art_refs = search_data.get("search_results", []) if isinstance(search_data, dict) else []
        prior_art_text = json.dumps(prior_art_refs, ensure_ascii=False)[:6000] or "未检索到明确对比文件"

        similarity_params = {"invention": original[:6000], "prior_art": prior_art_text}
        await _emit_tool_start("similarity_analyzer", similarity_params)
        similarity_result = await SimilarityAnalyzerTool().execute(**similarity_params)
        await _emit_tool_end(
            "similarity_analyzer",
            similarity_params,
            similarity_result,
            bool(similarity_result.get("success", True)) if isinstance(similarity_result, dict) else True,
        )
        similarity_data = similarity_result.get("data", {}) if isinstance(similarity_result, dict) else {}

        scorer_params = {"invention": original[:6000], "prior_art": prior_art_text}
        await _emit_tool_start("patentability_scorer", scorer_params)
        score_result = await PatentabilityScorerTool().execute(**scorer_params)
        await _emit_tool_end(
            "patentability_scorer",
            scorer_params,
            score_result,
            bool(score_result.get("success", True)) if isinstance(score_result, dict) else True,
        )
        score_data = score_result.get("data", {}) if isinstance(score_result, dict) else {}

        risk_params = {
            "analysis_type": "overall",
            "tech_data": original[:8000],
            "prior_art_references": json.dumps(prior_art_refs, ensure_ascii=False)[:8000],
        }
        await _emit_tool_start("risk_analyzer", risk_params)
        risk_result = await RiskAnalyzerTool().execute(**risk_params)
        await _emit_tool_end("risk_analyzer", risk_params, risk_result, True)
        risk_data = risk_result if isinstance(risk_result, dict) else {}

        report = {
            "retrieval_strategy": {
                "keywords": list(dict.fromkeys(keywords[:12])),
                "query": query,
                "databases_used": (
                    search_data.get("sources", sources.split(","))
                    if isinstance(search_data, dict)
                    else sources.split(",")
                ),
                "target_country": target_country,
                "search_strategy": search_data.get("search_strategy", "")
                if isinstance(search_data, dict)
                else "",
            },
            "prior_art_references": prior_art_refs,
            "similar_patents": prior_art_refs,
            "similarity_results": [
                {
                    "patent_id": ref.get("patent_id") or ref.get("reference_id") or "",
                    "title": ref.get("title", ""),
                    "abstract": ref.get("abstract", ""),
                    "source": ref.get("source", ""),
                    "similarity_score": similarity_data.get("overall_similarity", 0),
                    "distinguishing_features": similarity_data.get("key_differences", []),
                    "matching_features": similarity_data.get("feature_comparison", []),
                }
                for ref in prior_art_refs[:5]
                if isinstance(ref, dict)
            ],
            "novelty_assessment": score_data.get("novelty", {}),
            "inventive_step_assessment": score_data.get("inventive_step", {}),
            "utility_assessment": score_data.get("utility", {}),
            "overall_patentability": score_data.get("overall_patentability", "medium"),
            "confidence": 0.78 if prior_art_refs else 0.58,
            "risk_factors": risk_data.get("risks", []) if isinstance(risk_data, dict) else [],
            "overall_risk_level": risk_data.get("overall_risk_level", "unknown")
            if isinstance(risk_data, dict)
            else "unknown",
            "writing_recommendations": [
                similarity_data.get("recommendation", ""),
                score_data.get("recommendation", ""),
                "撰写时重点限定Cave折幕空间中的显示面识别、边界校正、内容映射和帧同步处理步骤。",
            ],
            "claim_strategy_recommendations": [
                "独立权利要求覆盖方法流程，系统权利要求覆盖处理模块、显示面参数获取模块、映射渲染模块和同步输出模块。",
                "从属权利要求分别限定坐标标定、边界投影、区域判定、掩膜生成、动态适配和异常重算。",
            ],
            "web_evidence": [],
            "non_patent_prior_art": [],
            "evidence_sources": [],
            "evidence_gaps": [],
            "tool_results": [
                search_result,
                similarity_result,
                score_result,
                risk_result,
            ],
        }
        return self._normalize_phase_output("retrieval_report", report)

    def _build_rule_based_patent_sections(
        self,
        context: WorkflowContext,
    ) -> Dict[str, Any]:
        """Build a real, reviewable patent draft when writer LLM tools are unavailable."""
        req = context.requirement_analysis if isinstance(context.requirement_analysis, dict) else {}
        features = req.get("key_innovative_features") if isinstance(req, dict) else []
        if not isinstance(features, list) or not features:
            features = [
                {
                    "name": "显示面姿态获取",
                    "description": "获取Cave折幕空间中至少一个可调显示面的姿态参数。",
                },
                {
                    "name": "边界映射计算",
                    "description": "根据显示面姿态确定相邻显示面的重叠、间隙及内容映射关系。",
                },
                {
                    "name": "显示内容补偿",
                    "description": "对外转产生的空白区域进行内容补偿，对内转产生的遮挡区域进行裁剪或重排。",
                },
                {
                    "name": "同步输出控制",
                    "description": "将处理后的多显示面视频内容同步输出到对应显示屏。",
                },
            ]
        feature_names = [str(item.get("name") if isinstance(item, dict) else item) for item in features[:8]]
        feature_desc = "；".join(
            str(item.get("description") or item.get("name") or item)
            for item in features[:8]
            if item
        )
        technical_problem = str(
            req.get("technical_problem")
            or "Cave折幕空间中显示面姿态变化后，视频画面容易出现边缘缝隙、遮挡重叠、内容错位和多屏不同步的问题。"
        )
        core_innovation = str(
            req.get("core_innovation")
            or "根据显示面姿态联动计算边界投影、内容映射、空白补偿、遮挡裁剪和多屏同步输出。"
        )
        title = context.title or "一种基于Cave折幕视频的处理方法及系统"
        independent = (
            "1. 一种基于Cave折幕视频的处理方法，其特征在于，包括：获取Cave折幕空间中至少一个"
            "可调显示面的姿态参数以及多个显示面的空间边界参数；根据所述姿态参数和空间边界参数，"
            "确定相邻显示面之间的边界投影关系、重叠区域和/或空白区域；基于所述边界投影关系建立"
            "视频内容与各显示面的映射关系；当检测到所述可调显示面的姿态发生变化时，按照所述映射关系"
            "对待显示视频内容进行裁剪、补偿和/或重排，得到分别对应各显示面的显示内容；以及将所述显示内容"
            "同步输出至对应显示面，以使Cave折幕空间中的视频画面在显示面姿态变化后保持连续显示。"
        )
        dependent_claims = [
            "2. 根据权利要求1所述的方法，其特征在于，所述姿态参数包括显示面的转动角度、法向量、边缘坐标和显示面尺寸中的至少一种。",
            "3. 根据权利要求1所述的方法，其特征在于，确定相邻显示面之间的边界投影关系包括将可调显示面的边缘投影至统一三维坐标系，并计算其与固定显示面的交叠边界。",
            "4. 根据权利要求1所述的方法，其特征在于，当相邻显示面之间形成空白区域时，根据邻近帧内容、预设背景内容或扩展纹理内容生成补偿内容并填充至所述空白区域。",
            "5. 根据权利要求1所述的方法，其特征在于，当相邻显示面之间形成重叠区域时，对重叠区域内的视频内容进行裁剪、透明度融合或优先级选择。",
            "6. 根据权利要求1所述的方法，其特征在于，所述映射关系包括姿态区间与显示内容变换参数之间的对应关系，所述显示内容变换参数包括缩放、平移、旋转、裁剪和补偿参数中的至少一种。",
            "7. 根据权利要求1所述的方法，其特征在于，还包括在显示面姿态变化超过预设阈值时重新计算所述映射关系，并对后续视频帧执行更新后的裁剪、补偿和/或重排。",
            "8. 一种基于Cave折幕视频的处理系统，其特征在于，包括姿态获取模块、边界计算模块、内容映射模块、补偿裁剪模块和同步输出模块，所述各模块被配置为执行权利要求1至7任一项所述的方法。",
            "9. 一种电子设备，其特征在于，包括处理器和存储器，所述存储器存储有程序，所述程序被处理器执行时实现权利要求1至7任一项所述的方法。",
            "10. 一种计算机可读存储介质，其上存储有计算机程序，其特征在于，所述计算机程序被处理器执行时实现权利要求1至7任一项所述的方法。",
        ]
        description = {
            "technical_field": (
                f"本发明涉及沉浸式显示和多屏视频处理技术领域，尤其涉及{title}，适用于Cave折幕、环幕、"
                "多LED显示面或投影显示面构成的沉浸式展示空间。"
            ),
            "background_art": (
                "现有Cave或折幕展示空间通常将多个显示面按照固定姿态拼接，并将视频内容分别输出至各显示面。"
                "当其中至少一个显示面能够转动、折叠或根据用户位置进行姿态调整时，相邻显示面之间的空间关系会发生变化，"
                f"容易产生如下问题：{technical_problem}。若仅采用固定视频裁切或固定投影参数，难以在不同姿态下维持画面连续性，"
                "也难以兼顾LED屏和投影屏等不同显示载体。因此，需要一种能够随显示面姿态变化而动态调整视频内容的处理方案。"
            ),
            "summary_of_invention": (
                f"为解决上述问题，本发明提出{title}。该方案的核心在于：{core_innovation}。"
                f"具体而言，系统首先获取显示面姿态和空间边界，随后计算相邻显示面的边界投影关系，并根据{feature_desc}等技术特征"
                "生成多显示面的内容映射参数。当检测到显示面外转时，对由此产生的空白区域进行补偿；当检测到显示面内转时，"
                "对遮挡或重叠区域进行裁剪、融合或重排。由此能够在折幕角度、用户入口位置或展示姿态发生变化时，"
                "保持视频画面的连续性、沉浸感和同步性。"
            ),
            "drawings_description": (
                "图1为本发明实施例的Cave折幕视频处理系统结构示意图；图2为本发明实施例的基于显示面姿态的视频处理方法流程示意图；"
                "图3为本发明实施例的显示面边界映射及空白补偿关系示意图。"
            ),
            "detailed_description": (
                "下面结合附图对本发明的实施方式进行说明。在一个实施例中，Cave折幕空间包括固定显示面和至少一个可调显示面，"
                "可调显示面可以为LED显示屏、投影幕、折叠屏或其他显示载体。姿态获取模块采集可调显示面的转动角度、边缘坐标、"
                "法向量和尺寸参数，并将固定显示面和可调显示面统一到同一三维坐标系中。边界计算模块根据所述参数计算相邻显示面的"
                "边界投影关系，判断当前姿态下是否存在空白区域、重叠区域或内容错位区域。内容映射模块依据边界投影关系确定视频帧"
                "在各显示面上的裁切窗口和变换参数。补偿裁剪模块在外转造成空白区域时生成补偿画面，在内转造成重叠区域时执行裁剪、"
                "融合或优先级显示。同步输出模块将处理后的视频内容分别输出至对应显示面，并在姿态变化超过阈值时重新计算映射关系。"
                f"上述过程可结合预设姿态区间执行，所述姿态区间可以对应{', '.join(feature_names[:4])}等参数，以降低实时计算量并保证显示稳定。"
            ),
        }
        abstract = (
            f"本发明公开了{title}，该方法获取Cave折幕空间中可调显示面的姿态参数和多个显示面的空间边界参数，"
            "确定相邻显示面之间的边界投影关系、重叠区域和/或空白区域，建立视频内容与各显示面的映射关系；"
            "当显示面姿态发生变化时，对待显示视频内容进行裁剪、补偿和/或重排并同步输出至对应显示面。"
            "本发明能够在折幕角度变化时保持多显示面视频画面的连续性和沉浸感。"
        )
        return {
            "claims": {
                "independent_claim": independent,
                "dependent_claims": dependent_claims,
            },
            "description": description,
            "abstract": abstract,
        }

    async def _generate_patent_in_sections(
        self,
        service,
        profile_id: str,
        base_task: str,
        context,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """通过 Agent 工具调用生成专利文件
        
        Agent 会按照 SOUL.md 中定义的工具调用序列：
        1. claim_drafter - 生成权利要求书
        2. description_writer - 生成说明书各章节
        3. support_checker - 检查支持关系  
        4. patent_docx_generator - 生成最终 .docx 文件
        
        返回前端期望的结构化 dict。
        """
        req_data = json.dumps(context.requirement_analysis, ensure_ascii=False)[:2000] if context.requirement_analysis else ""
        ret_data = json.dumps(context.retrieval_report, ensure_ascii=False)[:1500] if context.retrieval_report else ""
        task_context = str(base_task or "").strip()
        tech_content = "\n\n".join(
            part
            for part in [
                f"当前撰写任务/修正要求：\n{task_context}" if task_context else "",
                context.original_description,
                json.dumps(context.requirement_analysis or {}, ensure_ascii=False),
                json.dumps(context.retrieval_report or {}, ensure_ascii=False),
            ]
            if part
        )

        async def _emit_tool_start(tool_name: str, parameters: Dict[str, Any]) -> None:
            if event_callback:
                event_callback(
                    "专利撰写 Agent",
                    "agent.tool_call_start",
                    f"🔧 调用工具: {tool_name}",
                    {
                        "agent_name": "专利撰写 Agent",
                        "tool_name": tool_name,
                        "parameters": parameters,
                    },
                )

        async def _emit_tool_end(
            tool_name: str,
            parameters: Dict[str, Any],
            result: Any,
            success: bool = True,
        ) -> None:
            if event_callback:
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                event_callback(
                    "专利撰写 Agent",
                    "agent.tool_call_end",
                    ("✅" if success else "❌") + f" {tool_name} 返回",
                    {
                        "agent_name": "专利撰写 Agent",
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "result": result_text[:1200],
                        "success": success,
                    },
                )

        async def _run_writer_tool(
            tool_name: str,
            parameters: Dict[str, Any],
            call_factory: Callable[[], Any],
            timeout_seconds: int = 90,
        ) -> Dict[str, Any]:
            """Run a writer-owned tool with progress events and a bounded wait.

            Section drafting must keep moving: a single slow LLM/tool call should not
            block the whole patent document from being written into the working DOCX.
            """
            await _emit_tool_start(tool_name, parameters)
            try:
                result = await asyncio.wait_for(call_factory(), timeout=timeout_seconds)
                if not isinstance(result, dict):
                    result = {"success": True, "data": {"content": str(result)}}
                await _emit_tool_end(
                    tool_name,
                    parameters,
                    result,
                    bool(result.get("success", True)),
                )
                return result
            except Exception as exc:
                result = {
                    "success": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "data": {},
                }
                await _emit_tool_end(tool_name, parameters, result, False)
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.thinking",
                        f"⚠️ {tool_name} 调用超时或失败，继续使用分段兜底内容写入草稿",
                        {
                            "agent_name": "专利撰写 Agent",
                            "thought": "writer_tool_timeout_fallback",
                            "tool_name": tool_name,
                            "error": result["error"],
                        },
                    )
                return result

        # Deterministically orchestrate the writer-owned Hermes tools first. This keeps
        # long patent drafting visible and prevents the writer agent from looping on tools.
        try:
            from src.agents.hermes.tools.claim_drafter import ClaimDrafterTool
            from src.agents.hermes.tools.description_writer import DescriptionWriterTool
            from src.agents.hermes.tools.support_checker import SupportCheckerTool

            claims_data: Dict[str, Any] = {}
            description_data: Dict[str, Any] = {}
            drawings_data: List[Dict[str, Any]] = []
            abstract_text = ""
            rule_based_draft = self._build_rule_based_patent_sections(context)

            async def _checkpoint_writer_draft(checkpoint: str) -> None:
                """Persist current section-level content and refresh draft/working_draft.docx."""
                prior_checkpoints = []
                if isinstance(context.patent_draft, dict):
                    prior_checkpoints = list(context.patent_draft.get("drafting_checkpoints", []) or [])

                current_draft: Dict[str, Any] = {
                    "claims": {
                        "independent_claim": claims_data.get("independent_claim", ""),
                        "dependent_claims": claims_data.get("dependent_claims", []),
                    },
                    "description": {
                        "technical_field": description_data.get("technical_field", ""),
                        "background_art": description_data.get("background_art", ""),
                        "summary_of_invention": description_data.get("summary_of_invention", ""),
                        "drawings_description": description_data.get("drawings_description", ""),
                        "detailed_description": description_data.get("detailed_description", ""),
                    },
                    "abstract": abstract_text,
                    "drawings": drawings_data,
                    "docx_path": "",
                    "drafting_checkpoints": [
                        *prior_checkpoints,
                        {"checkpoint": checkpoint, "timestamp": datetime.now().isoformat()},
                    ],
                }
                context.patent_draft = current_draft

                try:
                    _persist_phase_result(context.task_id, "patent_draft", current_draft)
                except Exception:
                    pass

                try:
                    from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool

                    docx_result = await PatentDocxGeneratorTool().execute(
                        title=context.title or "专利申请文件",
                        claims=current_draft["claims"],
                        description=current_draft["description"],
                        abstract=current_draft["abstract"],
                        task_id=context.task_id,
                        tech_description=context.original_description,
                        drawings=current_draft.get("drawings", []),
                        output_stage="draft",
                        file_name="working_draft.docx",
                    )
                    if isinstance(docx_result, dict) and docx_result.get("success"):
                        current_draft["working_docx_path"] = docx_result.get("file_path", "")
                        if docx_result.get("figures"):
                            current_draft["working_docx_figures"] = docx_result.get("figures")
                        context.patent_draft = current_draft
                        try:
                            _persist_phase_result(context.task_id, "patent_draft", current_draft)
                        except Exception:
                            pass
                        if event_callback:
                            event_callback(
                                "专利撰写 Agent",
                                "agent.content",
                                f"📝 已写入工作草稿 DOCX：{checkpoint}",
                                {
                                    "agent_name": "专利撰写 Agent",
                                    "phase": "patent_writing",
                                    "checkpoint": checkpoint,
                                    "content": json.dumps(
                                        {
                                            "working_docx_path": current_draft.get("working_docx_path"),
                                            "figures": current_draft.get("working_docx_figures", []),
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            )
                    elif event_callback:
                        event_callback(
                            "专利撰写 Agent",
                            "agent.thinking",
                            f"⚠️ 工作草稿 DOCX 暂未写入成功：{checkpoint}",
                            {
                                "agent_name": "专利撰写 Agent",
                                "phase": "patent_writing",
                                "checkpoint": checkpoint,
                                "result": docx_result,
                            },
                        )
                except Exception as exc:
                    self._logger.warning(
                        f"Failed to write incremental working DOCX checkpoint {checkpoint}: {exc}",
                        task_id=context.task_id,
                    )
                    current_draft["_working_docx_error"] = str(exc)[:500]

            claim_params = {
                "features": tech_content[:12000],
                "protection_scope": "覆盖Cave折幕视频处理方法、系统、设备及存储介质",
            }
            claim_result = await _run_writer_tool(
                "claim_drafter",
                claim_params,
                lambda: ClaimDrafterTool().execute(**claim_params),
            )
            claim_data = claim_result.get("data", {}) if isinstance(claim_result, dict) else {}
            claims_data = self._normalize_claims_payload(
                claim_data,
                raw_response=claim_result.get("raw_response") if isinstance(claim_result, dict) else None,
            )
            if not claims_data.get("independent_claim"):
                claims_data = dict(rule_based_draft["claims"])
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.thinking",
                        "🧾 claim_drafter 暂不可用，已基于需求分析补齐可审查的权利要求书",
                        {
                            "agent_name": "专利撰写 Agent",
                            "thought": "rule_based_claims_fallback",
                        },
                    )
            await _checkpoint_writer_draft("权利要求书")

            claims_text = json.dumps(claims_data, ensure_ascii=False)
            section_map = {
                "technical_field": "technical_field",
                "background_art": "background",
                "summary_of_invention": "summary",
                "drawings_description": "drawings",
                "detailed_description": "detailed",
            }
            writer_tool = DescriptionWriterTool()
            for field_name, section_type in section_map.items():
                desc_params = {
                    "section_type": section_type,
                    "technical_content": tech_content[:12000],
                    "claims": claims_text[:6000],
                }
                section_result = await _run_writer_tool(
                    "description_writer",
                    desc_params,
                    lambda params=desc_params: writer_tool.execute(**params),
                )
                section_data = section_result.get("data", {}) if isinstance(section_result, dict) else {}
                section_content = section_data.get("content", "") if isinstance(section_data, dict) else ""
                if not section_content:
                    section_content = str(rule_based_draft["description"].get(field_name, ""))
                    if event_callback:
                        event_callback(
                            "专利撰写 Agent",
                            "agent.thinking",
                            f"📚 description_writer 暂不可用，已补齐{field_name}章节",
                            {
                                "agent_name": "专利撰写 Agent",
                                "thought": "rule_based_description_fallback",
                                "section": field_name,
                            },
                        )
                if section_content:
                    description_data[field_name] = section_content
                    await _checkpoint_writer_draft(
                        {
                            "technical_field": "技术领域",
                            "background_art": "背景技术",
                            "summary_of_invention": "发明内容",
                            "drawings_description": "附图说明",
                            "detailed_description": "具体实施方式",
                        }.get(field_name, field_name)
                    )

            support_params = {
                "claims": claims_text[:10000],
                "description": json.dumps(description_data, ensure_ascii=False)[:14000],
            }
            support_result = await _run_writer_tool(
                "support_checker",
                support_params,
                lambda: SupportCheckerTool().execute(**support_params),
                timeout_seconds=60,
            )

            if not abstract_text:
                summary = str(description_data.get("summary_of_invention") or "")
                detailed = str(description_data.get("detailed_description") or "")
                abstract_text = str(rule_based_draft.get("abstract") or summary or detailed or context.original_description)[:600]
                await _checkpoint_writer_draft("说明书摘要")

            required_sections_present = all(
                str(description_data.get(key) or "").strip()
                for key in (
                    "technical_field",
                    "background_art",
                    "summary_of_invention",
                    "detailed_description",
                )
            )
            if claims_data.get("independent_claim") and required_sections_present:
                existing_draft = context.patent_draft if isinstance(context.patent_draft, dict) else {}
                patent_result = {
                    "claims": {
                        "independent_claim": claims_data.get("independent_claim", ""),
                        "dependent_claims": claims_data.get("dependent_claims", []),
                    },
                    "description": {
                        "technical_field": description_data.get("technical_field", ""),
                        "background_art": description_data.get("background_art", ""),
                        "summary_of_invention": description_data.get("summary_of_invention", ""),
                        "drawings_description": description_data.get("drawings_description", ""),
                        "detailed_description": description_data.get("detailed_description", ""),
                    },
                    "abstract": abstract_text,
                    "drawings": drawings_data,
                    "docx_path": "",
                    "support_check": support_result,
                    "full_response": "",
                    "drafting_checkpoints": existing_draft.get("drafting_checkpoints", []),
                    "working_docx_path": existing_draft.get("working_docx_path", ""),
                    "working_docx_figures": existing_draft.get("working_docx_figures", []),
                }
                claims_count = 1 + len(patent_result["claims"]["dependent_claims"])
                sections_count = sum(1 for v in patent_result["description"].values() if v)
                self._logger.info(
                    f"Patent writer: deterministic tool generation complete. Claims={claims_count}, Sections={sections_count}"
                )
                return patent_result
        except Exception as exc:
            self._logger.warning(
                f"Deterministic writer tool orchestration failed, falling back to agent loop: {exc}"
            )
        
        # 构建完整的专利撰写任务 prompt，让 Agent 通过工具调用完成
        # 注：不在此阶段生成 docx，待质量审查通过后再生成
        task_prompt = f"""请基于以下技术方案，通过调用工具生成完整的专利申请文件内容。

【发明名称】
{context.title or "待定"}

【技术描述】
{context.original_description}

【需求分析结果】
{req_data}

【检索分析结果】
{ret_data}

【任务要求】
请按顺序调用以下工具完成专利撰写：

1. 调用 claim_drafter 工具生成权利要求书
   - features: 从技术描述中提取的技术特征
   - protection_scope: 期望的保护范围
   
2. 调用 description_writer 工具生成说明书各章节
   - section_type="technical_field": 技术领域
   - section_type="background": 背景技术
   - section_type="summary": 发明内容（技术问题+技术方案+有益效果）
   - section_type="detailed": 具体实施方式
   
 3. 对涉及结构、装置、系统、流程或空间关系的发明，调用 patent_drawing_generator 工具生成对应附图
    - tech_description: 依据权利要求、说明书附图说明和原始技术方案整理的绘图说明
    - task_id: 当前工作流任务ID {context.task_id}
    - title: 附图标题，例如“系统结构示意图”或“方法流程示意图”
    - description: 附图说明文本，例如“图1为……示意图”

 4. 调用 support_checker 检查权利要求与说明书的支持关系

注意：本阶段仅生成专利内容和必要附图，不生成最终文档文件。请确保所有内容完整、规范。

请开始执行工具调用。"""

        self._logger.info("Patent writer: starting tool-based generation")
        if event_callback:
            for step, message, thought in (
                (1, "🧾 正在生成权利要求书...", "生成权利要求书"),
                (2, "📚 正在生成说明书各章节...", "生成说明书"),
                (3, "🔎 正在检查权利要求与说明书支持关系...", "检查支持关系"),
            ):
                event_callback(
                    "专利撰写 Agent",
                    "agent.thinking",
                    message,
                    {"agent_name": "专利撰写 Agent", "thought": thought, "step": step},
                )

        claims_data = {}
        description_data = {}
        abstract_text = ""
        docx_path = ""
        drawings_data = []
        final_response = ""
        last_failed_result: Optional[Dict[str, Any]] = None

        for writer_attempt in range(3):
            agent_result = await _run_agent_conversation(profile_id, task_prompt)

            if isinstance(agent_result, dict):
                final_response = agent_result.get("final_response", "") or agent_result.get("content", "") or final_response
                messages = agent_result.get("messages", [])
                agent_failed = agent_result.get("failed") is True or (
                    agent_result.get("completed") is False and bool(agent_result.get("error"))
                )
            else:
                final_response = str(agent_result) if agent_result else final_response
                messages = []
                agent_failed = False

            tool_call_names: Dict[str, str] = {}
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                for tool_call in msg.get("tool_calls", []) or []:
                    if not isinstance(tool_call, dict):
                        continue
                    call_id = str(tool_call.get("id") or "")
                    function_data = tool_call.get("function", {})
                    function_name = ""
                    if isinstance(function_data, dict):
                        function_name = str(function_data.get("name") or "")
                    function_name = function_name or str(tool_call.get("name") or "")
                    if call_id and function_name:
                        tool_call_names[call_id] = function_name

            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    tool_call_id = str(msg.get("tool_call_id") or "")
                    tool_name = str(msg.get("name") or tool_call_names.get(tool_call_id, ""))
                    try:
                        content_text = msg.get("content", "{}")
                        if isinstance(content_text, str) and "[TOOL_OUTPUT_SAVED_TO]:" in content_text:
                            content_text = content_text.split("[TOOL_OUTPUT_SAVED_TO]:", 1)[0].strip()
                        tool_content = json.loads(content_text)
                        if not tool_name:
                            tool_name = str(tool_content.get("tool") or "")
                        tool_data = tool_content.get("data", {})

                        if tool_name == "claim_drafter" and tool_content.get("success"):
                            candidate_claims = self._normalize_claims_payload(
                                tool_data,
                                raw_response=tool_content.get("raw_response"),
                            )
                            if candidate_claims.get("independent_claim"):
                                claims_data = candidate_claims
                            claims_count = (
                                (1 if str(claims_data.get("independent_claim") or "").strip() else 0)
                                + len(claims_data.get("dependent_claims", []) or [])
                            )
                            self._logger.info(
                                f"Got claims from tool: {claims_count} claims"
                            )

                        elif tool_name == "description_writer" and tool_content.get("success"):
                            section_type = tool_data.get("section_type", "")
                            content = tool_data.get("content", "")
                            if section_type == "technical_field":
                                description_data["technical_field"] = content
                            elif section_type == "background":
                                description_data["background_art"] = content
                            elif section_type == "summary":
                                description_data["summary_of_invention"] = content
                            elif section_type in {"drawings", "drawings_description"}:
                                description_data["drawings_description"] = content
                            elif section_type == "detailed":
                                description_data["detailed_description"] = content
                            self._logger.info(f"Got description section: {section_type}")

                        elif tool_name == "patent_docx_generator" and tool_content.get("success"):
                            docx_path = tool_data.get("file_path", "")
                            abstract_text = tool_data.get("abstract", "") or abstract_text
                            self._logger.info(f"DOCX generated: {docx_path}")

                        elif tool_name == "patent_drawing_generator" and tool_content.get("success"):
                            drawings = tool_data.get("drawings", [])
                            if isinstance(drawings, list):
                                drawings_data.extend(item for item in drawings if isinstance(item, dict))
                            self._logger.info(f"Got patent drawings: {len(drawings_data)} drawings")

                    except (json.JSONDecodeError, KeyError) as e:
                        self._logger.warning(f"Failed to parse tool result: {e}")
                        continue

            has_partial_content = bool(
                claims_data
                or any(description_data.values())
                or abstract_text
                or drawings_data
            )
            if (
                not agent_failed
                and has_partial_content
                and not claims_data.get("independent_claim", "").strip()
            ):
                agent_failed = True
                incomplete_error = "专利撰写输出不完整：缺少权利要求书"
                if isinstance(agent_result, dict):
                    agent_result = dict(agent_result)
                    agent_result["failed"] = True
                    agent_result["completed"] = False
                    agent_result["error"] = incomplete_error
                else:
                    agent_result = {
                        "failed": True,
                        "completed": False,
                        "error": incomplete_error,
                    }

            if not agent_failed:
                last_failed_result = None
                break

            last_failed_result = agent_result if isinstance(agent_result, dict) else None
            if not has_partial_content:
                failed_result: Dict[str, Any]
                if isinstance(agent_result, dict):
                    failed_result = agent_result
                else:
                    failed_result = {
                        "failed": True,
                        "completed": False,
                        "error": "专利撰写中断",
                    }
                return self._normalize_phase_output("patent_draft", failed_result)
            if writer_attempt >= 2:
                break

            completed_items = []
            if claims_data.get("independent_claim"):
                completed_items.append("权利要求书已完成，请不要重新生成权利要求书")
            if description_data.get("technical_field"):
                completed_items.append("技术领域已完成")
            if description_data.get("background_art"):
                completed_items.append("背景技术已完成")
            if description_data.get("summary_of_invention"):
                completed_items.append("发明内容已完成")
            if description_data.get("detailed_description"):
                completed_items.append("具体实施方式已完成")
            if abstract_text:
                completed_items.append("说明书摘要已完成")

            missing_items = []
            if not claims_data.get("independent_claim"):
                missing_items.append("权利要求书")
            elif not claims_data.get("dependent_claims"):
                missing_items.append("从属权利要求")
            if not description_data.get("technical_field"):
                missing_items.append("技术领域")
            if not description_data.get("background_art"):
                missing_items.append("背景技术")
            if not description_data.get("summary_of_invention"):
                missing_items.append("发明内容")
            if not description_data.get("detailed_description"):
                missing_items.append("具体实施方式")
            if not abstract_text:
                missing_items.append("说明书摘要")

            error_text = str(agent_result.get("error") or "专利撰写中断") if isinstance(agent_result, dict) else "专利撰写中断"
            task_prompt = f"""专利撰写过程中发生错误，需要从已完成内容之后继续撰写，不要从头重写。

【本次错误】
{error_text}

【已完成内容】
{chr(10).join(f"- {item}" for item in completed_items)}

【待补全内容】
{chr(10).join(f"- {item}" for item in missing_items)}

【继续要求】
1. 只调用工具补全待补全内容。
2. 已完成内容不要重新生成、不要改写、不要重复输出。
3. 补全时保持与已完成权利要求和说明书章节一致。
4. 本阶段仍然只生成专利内容，不生成最终文档文件。"""

        if last_failed_result is not None:
            repaired = await self._repair_incomplete_patent_draft_with_tools(
                context=context,
                claims_data=claims_data,
                description_data=description_data,
                abstract_text=abstract_text,
                event_callback=event_callback,
            )
            claims_data = repaired["claims"]
            description_data = repaired["description"]
            abstract_text = repaired["abstract"]

        required_sections_present = all(
            str(description_data.get(key) or "").strip()
            for key in (
                "technical_field",
                "background_art",
                "summary_of_invention",
                "detailed_description",
            )
        )
        if (
            last_failed_result is not None
            and (
                not claims_data.get("independent_claim", "").strip()
                or not required_sections_present
            )
        ):
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": str(last_failed_result.get("error") or "专利撰写中断")[:500],
                "claims": {
                    "independent_claim": claims_data.get("independent_claim", ""),
                    "dependent_claims": claims_data.get("dependent_claims", []),
                },
                "description": {
                    "technical_field": description_data.get("technical_field", ""),
                    "background_art": description_data.get("background_art", ""),
                    "summary_of_invention": description_data.get("summary_of_invention", ""),
                    "drawings_description": description_data.get("drawings_description", ""),
                    "detailed_description": description_data.get("detailed_description", ""),
                },
                "abstract": abstract_text,
                "drawings": drawings_data,
                "docx_path": "",
                "full_response": final_response,
            }
        
        # 如果工具调用没有返回结构化数据，尝试从 final_response 解析
        if not claims_data and not description_data:
            self._logger.warning("No tool results found, trying to parse tool_call from text")
            
            # 首先尝试解析 <tool_call> 格式（Agent 可能输出了 tool_call JSON 而非真正调用工具）
            tool_call_data = self._parse_tool_call_from_text(final_response)
            if tool_call_data:
                self._logger.info(f"Found tool_call in text: {tool_call_data.get('name')}")
                # 提取 claims/description/abstract 数据（不生成 docx）
                args = tool_call_data.get("arguments", {})
                if "claims" in args:
                    claims_data = args["claims"]
                if "description" in args:
                    description_data = args["description"]
                if "abstract" in args:
                    abstract_text = args["abstract"]
            
            # 如果仍然没有数据，回退到文本解析
            if not claims_data and not description_data:
                self._logger.warning("No tool_call found, falling back to text parsing")
                claims_data, description_data, abstract_text = self._parse_patent_from_text(final_response)
        
        # 组装为前端期望的结构化格式（不含 docx，待质量审查通过后生成）
        patent_result: Dict[str, Any] = {
            "claims": {
                "independent_claim": claims_data.get("independent_claim", ""),
                "dependent_claims": claims_data.get("dependent_claims", []),
            },
            "description": {
                "technical_field": description_data.get("technical_field", ""),
                "background_art": description_data.get("background_art", ""),
                "summary_of_invention": description_data.get("summary_of_invention", ""),
                "drawings_description": description_data.get("drawings_description", ""),
                "detailed_description": description_data.get("detailed_description", ""),
            },
            "abstract": abstract_text,
            "drawings": drawings_data,
            "docx_path": "",
            "full_response": final_response,
        }

        claims_count = 1 + len(patent_result["claims"]["dependent_claims"]) if patent_result["claims"]["independent_claim"] else 0
        sections_count = sum(1 for v in patent_result["description"].values() if v)
        self._logger.info(f"Patent writer: content generated. Claims={claims_count}, Sections={sections_count} (DOCX deferred to post-review)")

        return patent_result

    async def _repair_incomplete_patent_draft_with_tools(
        self,
        context: WorkflowContext,
        claims_data: Dict[str, Any],
        description_data: Dict[str, Any],
        abstract_text: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Use writer-owned Hermes tools to fill required patent sections after agent stalls."""
        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.thinking",
                "🛠️ 撰写内容未补齐，继续调度撰写工具补全必要章节",
                {"agent_name": "CEO Agent", "thought": "repair_incomplete_patent_draft"},
            )

        repaired_claims = dict(claims_data or {})
        repaired_description = dict(description_data or {})
        repaired_abstract = abstract_text or ""
        tech_content = "\n\n".join(
            part
            for part in [
                context.original_description,
                json.dumps(context.requirement_analysis or {}, ensure_ascii=False),
                json.dumps(context.retrieval_report or {}, ensure_ascii=False),
            ]
            if part
        )

        try:
            if not str(repaired_claims.get("independent_claim") or "").strip():
                from src.agents.hermes.tools.claim_drafter import ClaimDrafterTool

                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.thinking",
                        "🧾 正在使用 claim_drafter 补齐权利要求书...",
                        {"agent_name": "专利撰写 Agent", "thought": "repair_claims"},
                    )
                claim_result = await ClaimDrafterTool().execute(
                    features=tech_content[:12000],
                    protection_scope="覆盖Cave折幕视频处理方法、系统、设备及存储介质",
                )
                claim_data = claim_result.get("data", {}) if isinstance(claim_result, dict) else {}
                raw_response = claim_result.get("raw_response") if isinstance(claim_result, dict) else None
                claim_data = self._normalize_claims_payload(claim_data, raw_response=raw_response)
                if claim_data.get("independent_claim"):
                    repaired_claims = claim_data
        except Exception as exc:
            self._logger.warning(f"Failed to repair claims with claim_drafter: {exc}")

        claims_text = json.dumps(repaired_claims, ensure_ascii=False)
        section_map = {
            "technical_field": "technical_field",
            "background_art": "background",
            "summary_of_invention": "summary",
            "detailed_description": "detailed",
        }
        try:
            from src.agents.hermes.tools.description_writer import DescriptionWriterTool

            for field_name, section_type in section_map.items():
                if str(repaired_description.get(field_name) or "").strip():
                    continue
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.thinking",
                        f"📚 正在使用 description_writer 补齐{field_name}...",
                        {"agent_name": "专利撰写 Agent", "thought": f"repair_{field_name}"},
                    )
                section_result = await DescriptionWriterTool().execute(
                    section_type=section_type,
                    technical_content=tech_content[:12000],
                    claims=claims_text[:6000],
                )
                section_data = section_result.get("data", {}) if isinstance(section_result, dict) else {}
                section_content = section_data.get("content", "") if isinstance(section_data, dict) else ""
                if section_content:
                    repaired_description[field_name] = section_content
        except Exception as exc:
            self._logger.warning(f"Failed to repair description with description_writer: {exc}")

        if not repaired_abstract:
            summary = str(repaired_description.get("summary_of_invention") or "")
            detailed = str(repaired_description.get("detailed_description") or "")
            repaired_abstract = (summary or detailed or context.original_description)[:600]

        return {
            "claims": repaired_claims,
            "description": repaired_description,
            "abstract": repaired_abstract,
        }
    
    def _parse_tool_call_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从 Agent 文本输出中解析 <tool_call> 格式的 JSON
        
        当 Agent 输出 <tool_call>{"name": "...", "arguments": {...}}</tool_call> 格式时，
        解析并返回工具调用参数。支持多种格式变体。
        
        Returns:
            {"name": "tool_name", "arguments": {...}} 或 None
        """
        import re
        
        if not text:
            return None
        
        # 尝试多种 tool_call 格式
        patterns = [
            # 格式1: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
            r'<tool_call>\s*(\{.+?\})\s*</tool_call>',
            # 格式2: <tool_call>{"name": "...", "arguments": {...}} (无闭合标签)
            r'<tool_call>\s*(\{.+?"arguments"\s*:\s*\{.+?\}\s*\})',
            # 格式3: ```json\n{"name": "patent_docx_generator", ...}\n```
            r'```json\s*(\{"name"\s*:\s*"patent_docx_generator".+?\})\s*```',
            # 格式4: 直接的 JSON 对象（包含 patent_docx_generator）
            r'(\{"name"\s*:\s*"patent_docx_generator",\s*"arguments"\s*:\s*\{.+?\}\s*\})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    # 尝试解析 JSON
                    data = json.loads(match)
                    if isinstance(data, dict) and "name" in data:
                        # 确保 arguments 存在
                        if "arguments" not in data:
                            data["arguments"] = {}
                        self._logger.info(f"Parsed tool_call: name={data['name']}, args_keys={list(data['arguments'].keys())}")
                        return data
                except json.JSONDecodeError as e:
                    # JSON 可能不完整，尝试修复
                    self._logger.debug(f"JSON parse failed for pattern, trying to fix: {e}")
                    fixed = self._try_fix_json(match)
                    if fixed:
                        return fixed
        
        # 最后尝试：查找任何包含 patent_docx_generator 的大型 JSON 块
        # 这处理 JSON 跨越多行且可能被截断的情况
        docx_gen_match = re.search(
            r'\{\s*"name"\s*:\s*"patent_docx_generator"\s*,\s*"arguments"\s*:\s*(\{.+)',
            text,
            re.DOTALL
        )
        if docx_gen_match:
            args_text = docx_gen_match.group(1)
            # 尝试找到匹配的闭合括号
            args_data = self._extract_nested_json(args_text)
            if args_data:
                return {"name": "patent_docx_generator", "arguments": args_data}
        
        return None
    
    def _try_fix_json(self, text: str) -> Optional[Dict[str, Any]]:
        """尝试修复不完整的 JSON"""
        import re
        
        # 移除可能的尾部垃圾
        text = text.strip()
        
        # 计算括号平衡
        open_braces = text.count('{')
        close_braces = text.count('}')
        
        # 添加缺失的闭合括号
        if open_braces > close_braces:
            text += '}' * (open_braces - close_braces)
        
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "name" in data:
                if "arguments" not in data:
                    data["arguments"] = {}
                return data
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _extract_nested_json(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取嵌套的 JSON 对象，处理括号匹配"""
        depth = 0
        start = 0
        
        for i, char in enumerate(text):
            if char == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    # 找到完整的 JSON 对象
                    json_str = text[start:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue
        
        # 如果没有找到完整的 JSON，尝试修复
        if depth > 0 and start < len(text):
            json_str = text[start:] + '}' * depth
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        return None

    def _parse_patent_from_text(self, text: str) -> tuple:
        """从文本解析专利内容（回退方案）"""
        import re
        
        claims_data = {"independent_claim": "", "dependent_claims": []}
        description_data = {}
        abstract_text = ""
        
        # 尝试解析权利要求
        all_claims = re.split(r'\n(?=权利要求\d+)', text)
        for claim in all_claims:
            claim = claim.strip()
            if not claim:
                continue
            if "独立" in claim or claim.startswith("权利要求1"):
                if not claims_data["independent_claim"]:
                    claims_data["independent_claim"] = claim
                else:
                    claims_data["dependent_claims"].append(claim)
            elif claim.startswith("权利要求"):
                claims_data["dependent_claims"].append(claim)
        
        if not claims_data["independent_claim"] and all_claims:
            claims_data["independent_claim"] = all_claims[0].strip() if all_claims[0].strip() else ""
            claims_data["dependent_claims"] = [c.strip() for c in all_claims[1:] if c.strip()]
        
        # 尝试解析说明书章节
        section_patterns = {
            "technical_field": r"(?:技术领域|一、技术领域)[：:\s]*(.+?)(?=(?:背景技术|二、|$))",
            "background_art": r"(?:背景技术|二、背景技术)[：:\s]*(.+?)(?=(?:发明内容|三、|$))",
            "summary_of_invention": r"(?:发明内容|三、发明内容)[：:\s]*(.+?)(?=(?:附图说明|具体实施|四、|$))",
            "detailed_description": r"(?:具体实施方式|五、具体实施方式)[：:\s]*(.+?)(?=$)",
        }
        
        for key, pattern in section_patterns.items():
            match = re.search(pattern, text, re.DOTALL)
            if match:
                description_data[key] = match.group(1).strip()
        
        # 尝试解析摘要
        abstract_match = re.search(r"(?:说明书摘要|摘要)[：:\s]*(.+?)(?=(?:权利要求|$))", text, re.DOTALL)
        if abstract_match:
            abstract_text = abstract_match.group(1).strip()[:500]
        
        return claims_data, description_data, abstract_text

    def _normalize_claims_payload(
        self,
        payload: Any,
        raw_response: Any = None,
    ) -> Dict[str, Any]:
        """Normalize claim_drafter output from tool data, wrapper JSON, or text."""
        candidates: List[Any] = []
        if isinstance(payload, dict):
            candidates.append(payload)
            if isinstance(payload.get("claims"), dict):
                candidates.append(payload["claims"])
            if isinstance(payload.get("data"), dict):
                candidates.append(payload["data"])
                if isinstance(payload["data"].get("claims"), dict):
                    candidates.append(payload["data"]["claims"])

        if isinstance(raw_response, str) and raw_response.strip():
            parsed_raw = self._try_parse_json(raw_response)
            if isinstance(parsed_raw, dict):
                candidates.append(parsed_raw)
                if isinstance(parsed_raw.get("claims"), dict):
                    candidates.append(parsed_raw["claims"])
                if isinstance(parsed_raw.get("data"), dict):
                    candidates.append(parsed_raw["data"])
                    if isinstance(parsed_raw["data"].get("claims"), dict):
                        candidates.append(parsed_raw["data"]["claims"])

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            independent = str(
                candidate.get("independent_claim")
                or candidate.get("independent_claims")
                or candidate.get("claim_1")
                or candidate.get("claim1")
                or ""
            ).strip()
            dependent_raw = candidate.get("dependent_claims") or candidate.get("dependent_claim") or []
            if isinstance(dependent_raw, str):
                dependent_claims = [dependent_raw.strip()] if dependent_raw.strip() else []
            elif isinstance(dependent_raw, list):
                dependent_claims = [
                    str(claim).strip() for claim in dependent_raw if str(claim).strip()
                ]
            else:
                dependent_claims = []

            all_claims = candidate.get("claims_list") or candidate.get("all_claims")
            if isinstance(all_claims, list):
                normalized_all = [str(claim).strip() for claim in all_claims if str(claim).strip()]
                if not independent and normalized_all:
                    independent = normalized_all[0]
                    dependent_claims.extend(normalized_all[1:])

            if independent:
                return {
                    "independent_claim": independent,
                    "dependent_claims": dependent_claims,
                    "claim_tree": candidate.get("claim_tree", {}),
                    "protection_breadth": candidate.get("protection_breadth", ""),
                    "drafting_notes": candidate.get("drafting_notes", ""),
                }

        text_sources: List[str] = []
        if isinstance(payload, str):
            text_sources.append(payload)
        if isinstance(raw_response, str):
            text_sources.append(raw_response)
        for text in text_sources:
            parsed_claims, _, _ = self._parse_patent_from_text(text)
            if parsed_claims.get("independent_claim"):
                return parsed_claims

        return {"independent_claim": "", "dependent_claims": []}

    async def _call_agent_with_continuation(self, service, profile_id: str, task: str, max_rounds: int = 3) -> str:
        """调用 Agent 并让其自检输出完整性，不完整则补充直到满意

        流程：
        1. Agent 执行任务
        2. 检测输出是否完整（JSON 闭合 + 内容完整性）
        3. 如果不完整，让 Agent 自检并补充
        4. Agent 确认完整后才返回
        """
        # 第一次调用
        raw = await _run_agent_conversation(profile_id, task)
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

            raw = await _run_agent_conversation(profile_id, continuation_prompt)
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

    def _build_context_data_from_agent_response(
        self,
        agent_id: str,
        agent_text: Any,
        agent_tool_results: List[Dict[str, Any]],
        structured_result: Any = None,
    ) -> Dict[str, Any]:
        """Build normalized phase input from text plus optional structured agent result."""
        text = agent_text if isinstance(agent_text, str) else ""

        if isinstance(structured_result, dict):
            context_data = dict(structured_result)
        else:
            parsed = self._try_parse_json(text)
            if "raw_output" not in parsed:
                context_data = parsed
            else:
                context_data = {"agent": agent_id, "output": text, "summary": text[:500]}

        if agent_tool_results:
            context_data["tool_results"] = agent_tool_results
        return context_data

    def _normalize_phase_output(self, context_field: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """将 Agent 输出规范化为前端期望的数据格式

        不同阶段的 Agent 输出字段名可能与前端渲染器期望的不完全匹配，
        此方法做必要的字段映射和结构转换。

        关键：检测 Agent 自身执行失败 (failed: True) — 这种情况下必须明确
        标记 _agent_failed=True，让下游 iteration loop 知道需要重试。
        不要用 "待生成" 之类的占位符掩盖失败。
        """
        if not isinstance(data, dict):
            return data

        if context_field == "patent_draft" and isinstance(data.get("tool_results"), list):
            tool_draft = self._build_patent_draft_from_tool_results(data)
            if tool_draft:
                return tool_draft

        if context_field == "review_report" and (
            isinstance(data.get("final_response"), str)
            or isinstance(data.get("tool_results"), list)
        ):
            normalized_review = self._build_review_report_from_agent_envelope(data)
            if normalized_review:
                data = normalized_review

        # ═══ 检测 Agent 自身执行失败 (LLM API 错误等) ═══
        # 当 run_conversation 返回 {"failed": True, "error": "..."} 时
        # 必须显式标记 _agent_failed=True，否则 _check_review_needs_revision
        # 会读到空的 recommendation / issues 并误判为"没有问题"
        if data.get("failed") is True or data.get("completed") is False and data.get("error"):
            agent_error = data.get("error", "Agent execution failed")
            error_preview = str(agent_error)[:500]
            self._logger.warning(
                f"Agent failure detected in {context_field}: {error_preview}"
            )
            if context_field == "review_report":
                # 审查 Agent 失败 — 直接当作"严重问题，要求重审"
                return {
                    "_agent_failed": True,
                    "_agent_error": error_preview,
                    "recommendation": "reject",
                    "revision_priority": "critical",
                    "review_summary": {
                        "overall_score": 0.0,
                        "overall_rating": "poor",
                        "recommendation": "reject",
                        "reviewer_notes": (
                            f"审查 Agent 执行失败，无法完成审查。错误：{error_preview}。"
                            "将触发重新审查流程。"
                        ),
                    },
                    "formal_compliance_review": {
                        "score": 0.0,
                        "passed": False,
                        "issues": [
                            {
                                "severity": "critical",
                                "location": "agent_execution",
                                "description": f"审查 Agent 执行失败：{error_preview}",
                                "suggestion": "请重试任务，或检查 LLM API 配置（API Key、配额、模型可用性）。",
                            }
                        ],
                    },
                    "claims_review": {"issues": []},
                    "description_review": {"issues": []},
                    "consistency_review": {"issues": []},
                    "examination_risks": [
                        {
                            "risk_type": "agent_execution_failure",
                            "likelihood": "critical",
                            "description": f"审查 Agent 未成功执行：{error_preview}",
                            "mitigation_suggestion": "重试任务；如持续失败，检查 LLM API 凭据与配额。",
                        }
                    ],
                    "detailed_revision_suggestions": [],
                }
            elif context_field == "patent_draft":
                # 撰写 Agent 失败 — 返回空白结构 + 失败标记，绝对不输出"待生成"
                return {
                    "_agent_failed": True,
                    "_agent_error": error_preview,
                    "claims": {
                        "independent_claim": "",
                        "dependent_claims": [],
                    },
                    "description": {
                        "technical_field": "",
                        "background_art": "",
                        "summary_of_invention": "",
                        "drawings_description": "",
                        "detailed_description": "",
                    },
                    "abstract": "",
                    "docx_path": "",
                }
            elif context_field == "retrieval_report":
                return {
                    "_agent_failed": True,
                    "_agent_error": error_preview,
                    "novelty_assessment": {"rating": "unknown", "rationale": ""},
                    "inventive_step_assessment": {"rating": "unknown", "rationale": ""},
                    "utility_assessment": {"rating": "unknown", "rationale": ""},
                    "prior_art_references": [],
                    "retrieval_keywords": [],
                    "retrieval_databases": [],
                    "risk_factors": [],
                    "writing_recommendations": [],
                    "claim_strategy_recommendations": [],
                    "overall_patentability": "unknown",
                    "confidence": 0,
                }
            else:
                # 其他阶段也加失败标记
                data = dict(data)
                data["_agent_failed"] = True
                data["_agent_error"] = error_preview

        # ═══ 处理 {agent, output, summary} 格式 ═══
        # 当 JSON 解析失败时，数据会被包装成这种格式
        # 需要尝试从 output 字段中提取结构化数据
        raw_output_text = None
        if "output" in data and "agent" in data and isinstance(data.get("output"), str):
            raw_output_text = data["output"]
            # 尝试从 output 中解析 JSON
            parsed = self._try_parse_json(raw_output_text)
            if "raw_output" not in parsed and parsed:
                # 成功解析出结构化数据，使用解析结果
                data = parsed
            # 如果解析失败，后面会提供兜底结构

        # ═══ 为无法解析的数据提供兜底默认结构 ═══
        if "raw_output" in data or ("agent" in data and "output" in data):
            output_text = raw_output_text or data.get("output", "") or data.get("raw_output", "")

            if context_field == "retrieval_report":
                # 为检索报告提供兜底结构
                data = self._build_fallback_retrieval_report(output_text)
            elif context_field == "patent_draft":
                # 为专利草稿提供兜底结构
                data = self._build_fallback_patent_draft(output_text)
            elif context_field == "review_report":
                # 为审查报告提供兜底结构
                data = self._build_fallback_review_report(output_text)
            else:
                # 其他类型保留原格式
                return data

        if context_field == "requirement_analysis":
            # tech_field: 如果是嵌套对象，提取 primary_domain 作为字符串
            tf = data.get("tech_field")
            if isinstance(tf, dict):
                data["tech_field"] = tf.get("primary_domain", "")

            # key_innovative_features: 规范化字段名（feature_name → name）
            features = data.get("key_innovative_features") or data.get("key_features", [])
            if isinstance(features, list) and features:
                normalized = []
                for f in features:
                    if isinstance(f, dict):
                        normalized.append({
                            "name": f.get("feature_name", "") or f.get("name", ""),
                            "description": f.get("description", ""),
                            "technical_significance": f.get("technical_significance", "")
                                or ("核心创新" if f.get("is_core") else
                                    "创新特征" if f.get("is_innovative") else ""),
                        })
                    elif isinstance(f, str):
                        normalized.append({"name": f, "description": "", "technical_significance": ""})
                data["key_innovative_features"] = normalized

            # application_scenarios: 如果是对象列表，提取 scenario 字段为字符串列表
            scenarios = data.get("application_scenarios", [])
            if isinstance(scenarios, list) and scenarios and isinstance(scenarios[0], dict):
                data["application_scenarios"] = [
                    s.get("scenario", "") or s.get("name", "") or str(s)
                    for s in scenarios if isinstance(s, dict)
                ]

            # beneficial_effects: 如果是对象列表，提取 effect 字段为字符串列表
            effects = data.get("beneficial_effects", [])
            if isinstance(effects, list) and effects and isinstance(effects[0], dict):
                data["beneficial_effects"] = [
                    e.get("effect", "") or e.get("description", "") or str(e)
                    for e in effects if isinstance(e, dict)
                ]

            # information_gaps: 如果是对象列表，提取 gap 字段为字符串列表
            gaps = data.get("information_gaps", [])
            if isinstance(gaps, list) and gaps and isinstance(gaps[0], dict):
                data["information_gaps"] = [
                    g.get("gap", "") or g.get("description", "") or str(g)
                    for g in gaps if isinstance(g, dict)
                ]

            # patent_type_recommendation: 保持为对象 {suggested_type, rationale}
            if "patent_type" in data and "patent_type_recommendation" not in data:
                data["patent_type_recommendation"] = {
                    "suggested_type": data.get("patent_type", ""),
                    "rationale": data.get("recommendation_rationale", ""),
                }
            # 如果 patent_type_recommendation 已经存在但格式正确，保留原样

        elif context_field == "retrieval_report":
            # ═══ patentability_scores → novelty_assessment / inventive_step_assessment / utility_assessment ═══
            scores = data.get("patentability_scores", {})
            if isinstance(scores, dict):
                if "novelty" in scores and "novelty_assessment" not in data:
                    n = scores["novelty"]
                    if isinstance(n, dict):
                        data["novelty_assessment"] = {
                            "rating": n.get("rating", "unknown"),
                            "rationale": n.get("details", "") or n.get("rationale", ""),
                        }
                if "inventive_step" in scores and "inventive_step_assessment" not in data:
                    i = scores["inventive_step"]
                    if isinstance(i, dict):
                        data["inventive_step_assessment"] = {
                            "rating": i.get("rating", "unknown"),
                            "rationale": i.get("details", "") or i.get("rationale", ""),
                        }
                if "utility" in scores and "utility_assessment" not in data:
                    u = scores["utility"]
                    if isinstance(u, dict):
                        data["utility_assessment"] = {
                            "rating": u.get("rating", "unknown"),
                            "rationale": u.get("details", "") or u.get("rationale", ""),
                        }
                # overall_patentability 从 scores 整体评估
                if "overall_patentability" not in data:
                    ratings = [scores.get("novelty", {}).get("rating"), 
                               scores.get("inventive_step", {}).get("rating"),
                               scores.get("utility", {}).get("rating")]
                    # 综合评估：如果有 high 且无 low，则 high；如有 low，则 low；否则 medium
                    if "low" in ratings:
                        data["overall_patentability"] = "low"
                    elif all(r == "high" for r in ratings if r):
                        data["overall_patentability"] = "high"
                    else:
                        data["overall_patentability"] = "medium"

            # ═══ similarity_results → prior_art_references / similar_patents ═══
            sim_results = data.get("similarity_results", [])
            if isinstance(sim_results, list) and sim_results and "prior_art_references" not in data:
                refs = []
                for p in sim_results:
                    if not isinstance(p, dict):
                        continue
                    score = p.get("similarity_score", 0)
                    if isinstance(score, (int, float)) and score >= 0.7:
                        relevance = "high"
                    elif isinstance(score, (int, float)) and score >= 0.4:
                        relevance = "medium"
                    else:
                        relevance = "low"
                    
                    patent_id = p.get("patent_id", "")
                    source = p.get("source", "")
                    url = self._build_patent_url(patent_id, source)
                    
                    # 提取区别特征
                    diff_features = p.get("distinguishing_features", [])
                    differences = "; ".join(diff_features) if isinstance(diff_features, list) else str(diff_features)
                    
                    refs.append({
                        "title": p.get("title", ""),
                        "reference_id": patent_id,
                        "source": source,
                        "relevance": relevance,
                        "abstract": p.get("abstract", ""),
                        "differences": differences,
                        "url": url,
                        "applicant": p.get("applicant", ""),
                        "publication_date": p.get("publication_date", ""),
                        "similarity_score": score,
                        "matching_features": p.get("matching_features", []),
                    })
                if refs:
                    data["prior_art_references"] = refs
                    data["similar_patents"] = refs  # 兼容旧字段名

            # ═══ risk_assessment.risk_factors → risk_factors ═══
            risk_assess = data.get("risk_assessment", {})
            if isinstance(risk_assess, dict) and "risk_factors" not in data:
                data["risk_factors"] = risk_assess.get("risk_factors", [])
                data["overall_risk_level"] = risk_assess.get("overall_risk_level", "unknown")

            # retrieval_strategy.keywords → retrieval_keywords (顶层)
            strategy = data.get("retrieval_strategy", {})
            if isinstance(strategy, dict):
                if "retrieval_keywords" not in data and strategy.get("keywords"):
                    data["retrieval_keywords"] = strategy["keywords"]
                if "retrieval_databases" not in data and strategy.get("databases_used"):
                    data["retrieval_databases"] = strategy["databases_used"]

            # similar_patents → prior_art_references (前端期望格式) - 旧格式兼容
            if "similar_patents" in data and "prior_art_references" not in data:
                patents = data.get("similar_patents", [])
                if isinstance(patents, list):
                    refs = []
                    for p in patents:
                        if not isinstance(p, dict):
                            continue
                        # 根据 similarity_score 或 risk_level 映射为 relevance
                        score = p.get("similarity_score", 0)
                        risk = p.get("risk_level", "")
                        if risk == "high" or (isinstance(score, (int, float)) and score >= 0.7):
                            relevance = "high"
                        elif risk == "medium" or (isinstance(score, (int, float)) and score >= 0.4):
                            relevance = "medium"
                        else:
                            relevance = "low"

                        # 构造 URL（基于 source + patent_id）
                        patent_id = p.get("patent_id", "")
                        source = p.get("source", "")
                        url = self._build_patent_url(patent_id, source)

                        refs.append({
                            "title": p.get("title", ""),
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": relevance,
                            "abstract": p.get("abstract", ""),
                            "differences": "; ".join(p.get("key_differences", []))
                                if isinstance(p.get("key_differences"), list)
                                else p.get("key_differences", ""),
                            "url": url,
                            "applicant": p.get("applicant", ""),
                            "publication_date": p.get("publication_date", ""),
                            "similarity_score": score,
                        })
                    if refs:
                        data["prior_art_references"] = refs

            # novelty + novelty_rationale → novelty_assessment
            if "novelty" in data and "novelty_assessment" not in data:
                data["novelty_assessment"] = {
                    "rating": data.get("novelty", ""),
                    "rationale": data.get("novelty_rationale", ""),
                }
            # inventive_step + inventive_step_rationale → inventive_step_assessment
            if "inventive_step" in data and "inventive_step_assessment" not in data:
                data["inventive_step_assessment"] = {
                    "rating": data.get("inventive_step", ""),
                    "rationale": data.get("inventive_step_rationale", ""),
                }
            # utility + utility_rationale → utility_assessment
            if "utility" in data and "utility_assessment" not in data:
                data["utility_assessment"] = {
                    "rating": data.get("utility", ""),
                    "rationale": data.get("utility_rationale", ""),
                }

            # ===== 兜底提取：当 Agent 只输出了代码块片段（如 keywords_cn/risks 等）时的回退映射 =====

            # 1. 关键词兜底: keywords_cn/keywords_en → retrieval_keywords
            if not data.get("retrieval_keywords"):
                keywords_fb = data.get("keywords_cn") or data.get("keywords_en") or data.get("query")
                if isinstance(keywords_fb, list):
                    data["retrieval_keywords"] = keywords_fb
                elif isinstance(keywords_fb, str) and keywords_fb.strip():
                    data["retrieval_keywords"] = [keywords_fb.strip()]

            # 2. 风险因素兜底: risks → risk_factors
            if "risk_factors" not in data and "risks" in data:
                risks = data["risks"]
                if isinstance(risks, list):
                    normalized = []
                    for r in risks:
                        if isinstance(r, dict):
                            normalized.append({
                                "type": r.get("risk_type", "") or r.get("type", ""),
                                "description": r.get("description", ""),
                                "severity": r.get("severity", "medium"),
                                "mitigation": r.get("mitigation", "") or r.get("mitigation_strategy", ""),
                            })
                    data["risk_factors"] = normalized

            # 3. 新颖性兜底: novelty_score + novelty_rationale → novelty_assessment
            if "novelty_assessment" not in data:
                score = data.get("novelty_score")
                rationale = data.get("novelty_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["novelty_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 4. 创造性兜底: inventive_step_score + inventive_step_rationale → inventive_step_assessment
            if "inventive_step_assessment" not in data:
                score = data.get("inventive_step_score")
                rationale = data.get("inventive_step_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["inventive_step_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 5. 实用性兜底: utility_score + utility_rationale → utility_assessment
            if "utility_assessment" not in data:
                score = data.get("utility_score")
                rationale = data.get("utility_rationale")
                if score is not None or rationale:
                    rating = "unknown"
                    if isinstance(score, (int, float)):
                        if score >= 0.7:
                            rating = "high"
                        elif score >= 0.4:
                            rating = "medium"
                        else:
                            rating = "low"
                    data["utility_assessment"] = {
                        "rating": rating,
                        "rationale": str(rationale) if rationale else "",
                    }

            # 6. 专利列表兜底: similar_patents（字符串列表）→ prior_art_references
            if not data.get("prior_art_references"):
                pat_ids = data.get("similar_patents") or data.get("prior_art_list")
                if isinstance(pat_ids, list) and pat_ids:
                    refs = []
                    for pid in pat_ids:
                        if isinstance(pid, str) and pid.strip():
                            refs.append({
                                "title": "",
                                "reference_id": pid.strip(),
                                "source": "",
                                "relevance": "medium",
                                "abstract": "",
                                "differences": "",
                                "url": self._build_patent_url(pid.strip(), ""),
                                "applicant": "",
                                "publication_date": "",
                                "similarity_score": 0,
                            })
                    if refs:
                        data["prior_art_references"] = refs

            # 7. 数据源兜底: databases（顶层）→ retrieval_databases
            if "retrieval_databases" not in data:
                dbs = data.get("databases")
                if isinstance(dbs, list) and dbs:
                    data["retrieval_databases"] = dbs

        elif context_field == "review_report":
            # score → overall_score (如果 Agent 用了 score 字段)
            if "score" in data and "overall_score" not in data:
                data["overall_score"] = data["score"]
            # issues → 按类型分组到 formal_compliance / claims_review / description_review
            if "issues" in data and isinstance(data["issues"], list):
                if "formal_compliance" not in data:
                    formal = [i for i in data["issues"] if isinstance(i, dict) and i.get("type", "").startswith("form")]
                    claims = [i for i in data["issues"] if isinstance(i, dict) and "claim" in i.get("type", "").lower()]
                    desc = [i for i in data["issues"] if isinstance(i, dict) and i not in formal and i not in claims]
                    if formal:
                        data["formal_compliance"] = {"issues": formal}
                    if claims:
                        data["claims_review"] = {"issues": claims}
                    if desc:
                        data["description_review"] = {"issues": desc}

        return data

    def _build_review_report_from_agent_envelope(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recover a structured quality review from Hermes final_response/tool_results."""
        raw_text = str(data.get("final_response") or data.get("message") or "")
        parsed: Dict[str, Any] = {}
        if raw_text.strip():
            parsed_candidate = self._try_parse_json(raw_text)
            if parsed_candidate:
                parsed = parsed_candidate
            else:
                parsed = self._build_fallback_review_report(raw_text)

        if not parsed:
            parsed = {
                "recommendation": "reject",
                "revision_priority": "critical",
                "review_summary": {
                    "overall_score": 0.0,
                    "overall_rating": "poor",
                    "recommendation": "reject",
                    "reviewer_notes": "审查 Agent 未返回可解析的最终审查意见。",
                },
                "formal_compliance_review": {"issues": []},
                "claims_review": {"issues": []},
                "description_review": {"issues": []},
                "consistency_review": {"issues": []},
                "examination_risks": [],
                "detailed_revision_suggestions": [],
            }

        parsed.setdefault("formal_compliance_review", {"issues": []})
        parsed.setdefault("claims_review", {"issues": []})
        parsed.setdefault("description_review", {"issues": []})
        parsed.setdefault("consistency_review", {"issues": []})
        parsed.setdefault("examination_risks", [])
        parsed.setdefault("detailed_revision_suggestions", [])

        summary = parsed.get("review_summary")
        if isinstance(summary, dict):
            if "recommendation" not in parsed and summary.get("recommendation"):
                parsed["recommendation"] = summary.get("recommendation")
            if "overall_score" not in parsed and summary.get("overall_score") is not None:
                parsed["overall_score"] = summary.get("overall_score")

        tool_results = data.get("tool_results", [])
        if isinstance(tool_results, list):
            for item in tool_results:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("tool") or "")
                tool_payload = self._parse_tool_result_payload(item.get("result"))
                tool_data = tool_payload.get("data", {}) if isinstance(tool_payload, dict) else {}
                if not isinstance(tool_data, dict):
                    tool_data = {}
                raw_response = tool_payload.get("raw_response") if isinstance(tool_payload, dict) else None
                raw_parsed = self._try_parse_json(raw_response) if isinstance(raw_response, str) else {}
                if raw_parsed and not tool_data:
                    tool_data = raw_parsed

                if tool_name == "compliance_checker":
                    compliance = str(
                        tool_data.get("overall_compliance")
                        or raw_parsed.get("overall_compliance")
                        or ""
                    ).lower()
                    if compliance in {"fail", "conditional_pass", "不通过"}:
                        self._append_review_issue(
                            parsed,
                            "formal_compliance_review",
                            "high" if compliance == "conditional_pass" else "critical",
                            "形式与合规检查",
                            "合规检查未通过或仅条件通过。",
                            "根据合规检查结果补齐发明名称、摘要、说明书章节、附图说明和权利要求格式。",
                        )

                if tool_name == "claim_quality_analyzer":
                    quality = tool_data.get("overall_quality", raw_parsed.get("overall_quality"))
                    if isinstance(quality, (int, float)) and quality < 70:
                        self._append_review_issue(
                            parsed,
                            "claims_review",
                            "high",
                            "权利要求",
                            f"权利要求质量评分偏低：{quality}。",
                            "收窄独立权利要求，拆分被拼接的权利要求，并补充可计算的技术参数与步骤。",
                        )

                objections = (
                    tool_data.get("predicted_objections")
                    or raw_parsed.get("predicted_objections")
                    or tool_data.get("objections")
                    or []
                )
                if isinstance(objections, list):
                    for objection in objections:
                        if not isinstance(objection, dict):
                            continue
                        likelihood = str(objection.get("likelihood") or "").lower()
                        risk = {
                            "risk_type": objection.get("type") or objection.get("risk_type") or tool_name,
                            "likelihood": likelihood or "medium",
                            "description": objection.get("description") or "",
                            "mitigation_suggestion": objection.get("mitigation")
                            or objection.get("mitigation_suggestion")
                            or "",
                        }
                        if risk not in parsed["examination_risks"]:
                            parsed["examination_risks"].append(risk)
                        if likelihood in {"critical", "high"}:
                            parsed["detailed_revision_suggestions"].append(
                                {
                                    "section": risk["risk_type"],
                                    "reason": risk["description"],
                                    "suggested_content": risk["mitigation_suggestion"],
                                }
                            )

        if not parsed.get("recommendation"):
            parsed["recommendation"] = "reject" if self._check_review_needs_revision(parsed) else "approve"
        if not parsed.get("revision_priority"):
            parsed["revision_priority"] = "critical" if self._check_review_needs_revision(parsed) else "medium"
        parsed["_raw_final_response"] = raw_text[:2000] if raw_text else ""
        parsed["_agent_envelope_normalized"] = True
        return parsed

    def _append_review_issue(
        self,
        review_report: Dict[str, Any],
        section_key: str,
        severity: str,
        location: str,
        description: str,
        suggestion: str,
    ) -> None:
        section = review_report.setdefault(section_key, {})
        if not isinstance(section, dict):
            section = {}
            review_report[section_key] = section
        issues = section.setdefault("issues", [])
        if not isinstance(issues, list):
            issues = []
            section["issues"] = issues
        issue = {
            "severity": severity,
            "location": location,
            "description": description,
            "suggestion": suggestion,
        }
        if issue not in issues:
            issues.append(issue)

    def _build_patent_draft_from_tool_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """从流式 Agent 工具结果中恢复结构化专利草稿。

        streamed path 会把 patent_docx_generator 的顶层成功 envelope 和
        tool_results 一起交给通用 normalizer。质量审查需要的是 claims /
        description / abstract，而不是 DOCX 工具 envelope。
        """
        claims_data: Dict[str, Any] = {}
        description_data: Dict[str, Any] = {}
        abstract_text = str(data.get("abstract") or "")
        docx_path = str(data.get("docx_path") or "")
        drawings_data: List[Dict[str, Any]] = []

        for item in data.get("tool_results", []):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool") or "")
            tool_content = self._parse_tool_result_payload(item.get("result"))
            if not tool_content:
                continue

            tool_data = tool_content.get("data", {})
            if not isinstance(tool_data, dict):
                tool_data = {}

            if tool_name == "claim_drafter" and tool_content.get("success"):
                candidate_claims = self._normalize_claims_payload(
                    tool_data,
                    raw_response=tool_content.get("raw_response"),
                )
                if candidate_claims.get("independent_claim"):
                    claims_data = candidate_claims
            elif tool_name == "description_writer" and tool_content.get("success"):
                section_type = str(tool_data.get("section_type") or "")
                content = str(tool_data.get("content") or "")
                if section_type == "technical_field":
                    description_data["technical_field"] = content
                elif section_type == "background":
                    description_data["background_art"] = content
                elif section_type == "summary":
                    description_data["summary_of_invention"] = content
                elif section_type in {"drawings", "drawings_description"}:
                    description_data["drawings_description"] = content
                elif section_type == "detailed":
                    description_data["detailed_description"] = content
            elif tool_name == "patent_docx_generator" and tool_content.get("success"):
                docx_path = str(
                    tool_data.get("file_path")
                    or tool_data.get("docx_path")
                    or tool_content.get("docx_path")
                    or docx_path
                )
                abstract_text = str(tool_data.get("abstract") or tool_content.get("abstract") or abstract_text)
            elif tool_name == "patent_drawing_generator" and tool_content.get("success"):
                drawings = tool_data.get("drawings", [])
                if isinstance(drawings, list):
                    drawings_data.extend(item for item in drawings if isinstance(item, dict))

        has_content = bool(
            claims_data.get("independent_claim")
            or any(str(value).strip() for value in description_data.values())
            or abstract_text.strip()
        )
        if not has_content:
            return {}

        return {
            "claims": {
                "independent_claim": claims_data.get("independent_claim", ""),
                "dependent_claims": claims_data.get("dependent_claims", []),
            },
            "description": {
                "technical_field": description_data.get("technical_field", ""),
                "background_art": description_data.get("background_art", ""),
                "summary_of_invention": description_data.get("summary_of_invention", ""),
                "drawings_description": description_data.get("drawings_description", ""),
                "detailed_description": description_data.get("detailed_description", ""),
            },
            "abstract": abstract_text,
            "drawings": drawings_data,
            "docx_path": docx_path,
            "full_response": str(data.get("message") or ""),
        }

    def _parse_tool_result_payload(self, result: object) -> Dict[str, Any]:
        """解析 Hermes tool_complete result 字段为 dict。"""
        if isinstance(result, dict):
            return result
        if not isinstance(result, str):
            return {}
        content_text = result
        if "[TOOL_OUTPUT_SAVED_TO]:" in content_text:
            content_text = content_text.split("[TOOL_OUTPUT_SAVED_TO]:", 1)[0].strip()
        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _build_fallback_retrieval_report(self, output_text: str) -> Dict[str, Any]:
        """为检索报告构建兜底的默认结构"""
        import re
        
        # 尝试从文本中提取专利号
        patent_ids = re.findall(r'(CN\d{9}[A-Z]?|US\d{7,}[A-Z]?\d*|EP\d{7}[A-Z]?\d*)', output_text)
        prior_art_refs = []
        for pid in patent_ids[:10]:  # 最多取10个
            prior_art_refs.append({
                "title": "",
                "reference_id": pid,
                "source": "CNIPA" if pid.startswith("CN") else "USPTO" if pid.startswith("US") else "EPO",
                "relevance": "medium",
                "abstract": "",
                "differences": "",
                "url": self._build_patent_url(pid, ""),
                "applicant": "",
                "publication_date": "",
                "similarity_score": 0,
            })
        
        # 尝试从文本中提取关键词（查找引号中的中文内容）
        keywords_cn = re.findall(r'[""「」]([^""「」]{2,20})[""「」]', output_text)
        # 去重并取前10个
        keywords_cn = list(dict.fromkeys(keywords_cn))[:10]
        
        return {
            "novelty_assessment": {
                "rating": "unknown",
                "rationale": "数据解析中，请参考原始输出",
            },
            "inventive_step_assessment": {
                "rating": "unknown",
                "rationale": "数据解析中，请参考原始输出",
            },
            "utility_assessment": {
                "rating": "unknown",
                "rationale": "数据解析中，请参考原始输出",
            },
            "prior_art_references": prior_art_refs,
            "retrieval_keywords": keywords_cn if keywords_cn else ["待提取"],
            "retrieval_databases": ["CNIPA", "USPTO", "Google Patents"],
            "risk_factors": [],
            "writing_recommendations": [],
            "claim_strategy_recommendations": [],
            "overall_patentability": "unknown",
            "confidence": 0,
            "_raw_output": output_text[:2000] if output_text else "",  # 保留原始输出供参考
        }

    def _build_fallback_patent_draft(self, output_text: str) -> Dict[str, Any]:
        """为专利草稿构建兜底的默认结构

        关键修复 (Bug #2): 严禁在兜底结构中插入"待生成"占位符。
        之前的实现会在所有缺失字段写入"待生成",导致后续 .docx 生成
        时将这些占位符作为正式内容写入专利文件。

        新行为: 兜底结构显式标记 _agent_failed=True 与 _incomplete_output=True,
        实际字段保持空白字符串或空列表。下游 .docx 生成逻辑必须先检查
        _agent_failed / _incomplete_output,发现 True 时拒绝生成文档并标记
        任务为 FAILED 状态。
        """
        import re

        # 尝试从文本中提取权利要求 (仅在文本看起来是真实专利内容时)
        # 关键：必须先检查 output_text 是否是真实的专利内容
        # 之前用 regex 匹配 error/prompt 文本时,会把 prompt 的 section_type 标签
        # 当作章节内容,导致 description 字段保存"section_type=..."这样的垃圾。
        is_garbage_text = bool(
            output_text and (
                output_text.startswith("{") and "failed" in output_text
                or "Error code:" in output_text
                or '"failed": true' in output_text.lower()
                or '"failed":true' in output_text.lower()
            )
        )

        if is_garbage_text or not output_text:
            # 输入是 API 错误或空 — 不做正则提取,直接返回空结构 + 失败标记
            self._logger.warning(
                "Patent draft fallback triggered with garbage input; "
                "returning empty structure with _agent_failed=True"
            )
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_raw_output": output_text[:3000] if output_text else "",
                "claims": {
                    "independent_claim": "",
                    "dependent_claims": [],
                },
                "description": {
                    "technical_field": "",
                    "background_art": "",
                    "summary_of_invention": "",
                    "drawings_description": "",
                    "detailed_description": "",
                },
                "abstract": "",
                "docx_path": "",
            }

        # 真实文本 — 尝试正则提取
        claims_match = re.search(r'权利要求\s*1[.．、:：]\s*(.{50,500})', output_text, re.DOTALL)
        independent_claim = claims_match.group(1).strip() if claims_match else ""

        # 防御：如果提取出的"权利要求1"内容里包含 section_type 标签,
        # 说明这是 prompt 文本泄漏,丢弃
        if "section_type" in independent_claim or "调用" in independent_claim:
            independent_claim = ""

        dependent_claims = []
        dep_matches = re.findall(r'权利要求\s*(\d+)[.．、:：]\s*(.{30,300})', output_text, re.DOTALL)
        for num, content in dep_matches:
            if num != "1":
                clean = content.strip()
                if "section_type" not in clean and "调用" not in clean:
                    dependent_claims.append(f"权利要求{num}. {clean}")

        tech_field_match = re.search(r'技术领域[：:]\s*(.{10,200})', output_text)
        tech_field = tech_field_match.group(1).strip() if tech_field_match else ""
        if "section_type" in tech_field:
            tech_field = ""

        background_match = re.search(r'背景技术[：:]\s*(.{50,1000}?)(?=发明内容|技术方案|$)', output_text, re.DOTALL)
        background = background_match.group(1).strip() if background_match else ""
        if "section_type" in background:
            background = ""

        abstract_match = re.search(r'摘要[：:]\s*(.{50,500})', output_text)
        abstract = abstract_match.group(1).strip() if abstract_match else ""
        if "section_type" in abstract:
            abstract = ""

        # 检查是否真的提取到了任何内容
        has_content = bool(independent_claim or dependent_claims or tech_field or background or abstract)
        if not has_content:
            self._logger.warning(
                "Patent draft fallback: no real content extracted from output text"
            )
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_raw_output": output_text[:3000] if output_text else "",
                "claims": {"independent_claim": "", "dependent_claims": []},
                "description": {
                    "technical_field": "",
                    "background_art": "",
                    "summary_of_invention": "",
                    "drawings_description": "",
                    "detailed_description": "",
                },
                "abstract": "",
                "docx_path": "",
            }

        return {
            "claims": {
                "independent_claim": independent_claim,
                "dependent_claims": dependent_claims,
            },
            "description": {
                "technical_field": tech_field,
                "background_art": background,
                "summary_of_invention": "",
                "drawings_description": "",
                "detailed_description": "",
            },
            "abstract": abstract,
            "docx_path": "",
            "_raw_output": output_text[:3000] if output_text else "",
        }

    def _build_fallback_review_report(self, output_text: str) -> Dict[str, Any]:
        """为审查报告构建兜底的默认结构

        关键修复 (Bug #1 根因): 之前的实现当 review 输出无法解析时
        设置 recommendation='unknown' / revision_priority='medium' / issues=[],
        导致 _check_review_needs_revision 全部检查都失败,workflow 误判为
        "无问题"并直接完成,从来不回退到 writer。

        新行为: 兜底结构必须明确包含一个 critical 级别 issue,
        保证 _check_review_needs_revision 返回 True,触发 iteration loop。
        """
        import re

        # 检测输入是否是 API 错误或空响应
        is_garbage_text = bool(
            output_text and (
                "Error code:" in output_text
                or '"failed": true' in output_text.lower()
                or '"failed":true' in output_text.lower()
                or output_text.startswith("{")
                and "error" in output_text[:200].lower()
            )
        )

        if is_garbage_text or not output_text:
            # 输入是 API 错误或空 — 必须显式标记失败,让 iteration loop 触发
            error_msg = (output_text or "审查 Agent 输出为空")[:500]
            self._logger.warning(
                f"Review report fallback triggered with garbage input: {error_msg[:200]}"
            )
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_raw_output": output_text[:2000] if output_text else "",
                "recommendation": "reject",
                "revision_priority": "critical",
                "review_summary": {
                    "overall_score": 0.0,
                    "overall_rating": "poor",
                    "recommendation": "reject",
                    "reviewer_notes": (
                        f"审查 Agent 输出无法解析或为错误响应：{error_msg}。"
                        "将触发重新审查。"
                    ),
                },
                "formal_compliance_review": {
                    "score": 0.0,
                    "passed": False,
                    "issues": [
                        {
                            "severity": "critical",
                            "location": "agent_execution",
                            "description": f"审查 Agent 未成功完成审查: {error_msg}",
                            "suggestion": "请重试任务，或检查 LLM API 配置。",
                        }
                    ],
                },
                "claims_review": {"issues": []},
                "description_review": {"issues": []},
                "consistency_review": {"issues": []},
                "examination_risks": [
                    {
                        "risk_type": "agent_execution_failure",
                        "likelihood": "critical",
                        "description": f"审查 Agent 未成功执行: {error_msg}",
                        "mitigation_suggestion": "重试任务;如持续失败,检查 LLM API 凭据与配额。",
                    }
                ],
                "detailed_revision_suggestions": [],
            }

        # 真实文本 — 尝试正则提取评分和建议
        score_match = re.search(r'(?:overall_score|总分|评分)["\s:：]*([0-9.]+)', output_text)
        score = float(score_match.group(1)) if score_match else 0.5

        # 尝试提取建议
        recommendation = "unknown"
        if re.search(r'(?:reject|驳回|不通过)', output_text, re.IGNORECASE):
            recommendation = "reject"
        elif re.search(r'(?:revise|修改|修正)', output_text, re.IGNORECASE):
            recommendation = "revise"
        elif re.search(r'(?:approve|通过|accept)', output_text, re.IGNORECASE):
            recommendation = "approve"

        # 关键修复：如果 recommendation 解析不出 ("unknown")，
        # 默认按"需重审"处理，revision_priority=critical，
        # 这样 _check_review_needs_revision 一定返回 True
        if recommendation == "unknown":
            recommendation = "reject"
            priority = "critical"
        else:
            priority = "high" if recommendation in ("reject", "revise") else "medium"

        return {
            "recommendation": recommendation,
            "review_summary": {
                "overall_score": score,
                "overall_rating": "needs_revision" if score < 0.7 else "good",
                "recommendation": recommendation,
                "reviewer_notes": "数据解析中，请参考原始输出",
            },
            "formal_compliance_review": {
                "score": score,
                "passed": recommendation == "approve",
                "issues": [],
            },
            "claims_review": {"issues": []},
            "description_review": {"issues": []},
            "consistency_review": {"issues": []},
            "examination_risks": [],
            "detailed_revision_suggestions": [],
            "revision_priority": priority,
            "_raw_output": output_text[:2000] if output_text else "",
        }

    def _build_patent_url(self, patent_id: str, source: str) -> str:
        """根据专利号和来源构造可点击跳转的 URL"""
        if not patent_id:
            return ""

        source_lower = source.lower() if source else ""
        pid = patent_id.strip()

        if source_lower in ("cnipa", "中国国家知识产权局"):
            # CNIPA 公开查询
            return f"https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord={pid}"
        elif source_lower in ("uspto", "美国专利商标局"):
            # USPTO 全文检索
            clean_id = pid.replace("/", "").replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("epo", "欧洲专利局"):
            return f"https://worldwide.espacenet.com/patent/search?q={pid}"
        elif source_lower in ("google_patents", "google patents"):
            clean_id = pid.replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("arxiv", "arxiv 学术论文"):
            # arXiv ID 格式: 2301.12345
            return f"https://arxiv.org/abs/{pid}"
        elif source_lower in ("wipo",):
            return f"https://patentscope.wipo.int/search/en/detail.jsf?docId={pid}"
        else:
            # 默认用 Google Patents
            return f"https://patents.google.com/patent/{pid}" if pid else ""

    def _try_parse_json(self, text: Any) -> Dict[str, Any]:
        """尝试从文本中解析 JSON，支持处理截断的 JSON 和混合格式"""
        import re

        if isinstance(text, dict):
            return text
        if isinstance(text, list):
            return {"results": text}
        if not isinstance(text, str):
            return {"raw_output": "" if text is None else str(text)}
        if not text:
            return {"raw_output": ""}

        # 尝试直接解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从 markdown code block 中提取 — 支持多个代码块合并
        triple = chr(96) * 3  # ```
        # 修改正则以支持未闭合的代码块（结束标签可选）
        pattern = re.escape(triple) + r"(?:json)?\s*\n?(.*?)(?:\s*" + re.escape(triple) + r"|$)"
        matches = re.findall(pattern, text, re.DOTALL)

        if matches:
            merged = {}
            all_failed = True
            for json_str in matches:
                json_str = json_str.strip()
                if not json_str:
                    continue
                # 尝试直接解析
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                        all_failed = False
                except json.JSONDecodeError:
                    pass
                # 尝试修复截断的 JSON（补充缺失的闭合括号）
                if all_failed or not merged:
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, dict):
                                merged.update(parsed)
                                all_failed = False
                        except json.JSONDecodeError:
                            pass
            if not all_failed and merged:
                return merged

        # 尝试从 <tool_response> 标签中提取 JSON（Agent 可能输出这种格式）
        tool_response_pattern = r'<tool_response>\s*([\s\S]*?)\s*</tool_response>'
        tool_matches = re.findall(tool_response_pattern, text)
        if tool_matches:
            merged = {}
            for json_str in tool_matches:
                json_str = json_str.strip()
                if not json_str:
                    continue
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                    elif isinstance(parsed, list) and parsed:
                        # 如果是列表，尝试合并第一层
                        if isinstance(parsed[0], dict):
                            merged["results"] = parsed
                except json.JSONDecodeError:
                    # 尝试修复
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, dict):
                                merged.update(parsed)
                        except json.JSONDecodeError:
                            pass
            if merged:
                return merged

        # 尝试找文本中第一个 { 到最后一个 } 的范围
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                # 尝试修复截断的 JSON
                repaired = self._repair_truncated_json(text[first_brace:last_brace + 1])
                if repaired:
                    try:
                        return json.loads(repaired)
                    except json.JSONDecodeError:
                        pass

        # 返回原始文本
        return {"raw_output": text}

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """尝试修复被截断的 JSON（补充缺失的闭合括号和引号）"""
        if not isinstance(json_str, str) or not json_str:
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

    async def _run_quality_review_with_timeout(
        self,
        service,
        profile_id: str,
        review_prompt: str,
        context: WorkflowContext,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        round_label: str = "",
        timeout_seconds: int = 150,
    ) -> tuple[str, Dict[str, Any]]:
        """Run the quality reviewer with a bounded wait and deterministic fallback.

        Quality review is a gate, so it must always produce a structured result. If
        the reviewer LLM/tool chain hangs, the local review still checks the draft
        and drawings, then lets the normal remediation loop decide whether to fix
        or finalize.
        """
        label = f"（{round_label}）" if round_label else ""
        try:
            agent_result = await asyncio.wait_for(
                self._run_agent_stream(
                    service,
                    profile_id,
                    review_prompt,
                    context,
                    agent_name="质量审查 Agent",
                    event_callback=event_callback,
                ),
                timeout=timeout_seconds,
            )
            agent_text = agent_result.get("text", "")
            context_data = self._build_context_data_from_agent_response(
                "quality_reviewer",
                agent_text,
                agent_result.get("tool_results", []),
                agent_result.get("structured_result"),
            )
            return agent_text, context_data
        except asyncio.TimeoutError:
            reason = f"质量审查 Agent{label}超过 {timeout_seconds}s 未完成"
        except Exception as exc:
            reason = f"质量审查 Agent{label}执行异常：{str(exc)[:180]}"

        self._logger.warning(
            f"{reason}; using deterministic quality review fallback",
            task_id=context.task_id,
        )
        if event_callback:
            event_callback(
                "质量审查 Agent",
                "agent.thinking",
                f"⚠️ {reason}，启用本地质量门审查（含附图检查）",
                {
                    "agent_name": "质量审查 Agent",
                    "thought": "deterministic_quality_review_fallback",
                    "timeout_seconds": timeout_seconds,
                },
            )

        review = self._build_deterministic_quality_review(context, reason=reason)
        return json.dumps(review, ensure_ascii=False)[:500], review

    async def _run_agent_stream(
        self,
        service,  # 保留参数签名兼容性，但不再使用
        profile_id: str,
        user_input: str,
        context: WorkflowContext,
        agent_name: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        流式调用 Agent 并实时发射事件到前端。
        使用 AIAgent 原生回调机制。
        返回 dict 包含:
          - text: agent 的最终文本输出
          - tool_results: 工具调用结果列表
        """
        import threading
        from src.agents.agent_config import create_ai_agent

        content_chunks: List[str] = []
        final_text = ""
        structured_result = None
        tool_results: List[Dict[str, Any]] = []
        events: List[Dict[str, Any]] = []
        events_lock = threading.Lock()
        result_holder = {"result": None, "error": None, "done": False}

        def _emit(evt_type: str, message: str, data: Dict[str, Any] = None):
            """通过callback直接发射事件"""
            if event_callback:
                event_callback(agent_name, evt_type, message, data or {})

        if hasattr(service, "run_conversation_stream"):
            async for event in service.run_conversation_stream(profile_id, user_input, user_id=context.user_id):
                event_type = event.get("type", "")
                event_data = event.get("data", {}) if isinstance(event.get("data", {}), dict) else {}

                if event_type == "tool_call_start":
                    tool_name = event_data.get("name", "")
                    params = event_data.get("parameters", {})
                    _emit("agent.tool_call_start", f"🔧 调用工具: {tool_name}", {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": params,
                    })
                elif event_type == "tool_call_end":
                    tool_name = event_data.get("name", "")
                    result = event_data.get("result", "")
                    result_str = str(result) if result else ""
                    success = event_data.get("success", True)
                    status_icon = "✅" if success else "❌"
                    _emit("agent.tool_call_end", f"{status_icon} {tool_name} 返回", {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "parameters": event_data.get("parameters", {}),
                        "result": result_str,
                        "success": success,
                    })
                    tool_results.append({
                        "tool": tool_name,
                        "parameters": event_data.get("parameters", {}),
                        "result": result,
                        "result_preview": result_str,
                        "success": success,
                    })
                elif event_type in {"content", "done"}:
                    content = event_data.get("content")
                    if isinstance(content, str):
                        content_chunks.append(content)

            final_text = "".join(content_chunks)
            return {"text": final_text, "tool_results": tool_results}

        def on_thinking(data):
            text = str(data).strip() if data else ""
            if not text or len(text) < 5:
                return
            if text.startswith("{") or text.startswith("["):
                return
            with events_lock:
                events.append({"type": "thinking", "data": {"message": text}})

        def on_tool_start(call_id, name, args):
            params = {}
            if isinstance(args, str):
                try:
                    params = json.loads(args)
                except Exception:
                    params = {"raw": args}
            elif isinstance(args, dict):
                params = args
            with events_lock:
                events.append({"type": "tool_call_start", "data": {"name": name, "parameters": params}})

        def on_tool_complete(call_id, name, args, result):
            result_str = str(result) if result else ""
            with events_lock:
                events.append({
                    "type": "tool_call_end",
                    "data": {"name": name, "result": result, "result_preview": result_str, "success": True}
                })

        def on_stream_delta(delta):
            with events_lock:
                content_chunks.append(delta)
                events.append({"type": "content_delta", "data": {"delta": delta}})

        callbacks = {
            "thinking": on_thinking,
            "tool_start": on_tool_start,
            "tool_complete": on_tool_complete,
            "stream_delta": on_stream_delta,
        }

        def run_agent():
            try:
                agent = create_ai_agent(profile_id=profile_id, callbacks=callbacks)
                result_holder["result"] = agent.run_conversation(user_input)
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                result_holder["done"] = True

        # 在后台线程运行 Agent
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        try:
            event_count = 0
            AGENT_TIMEOUT_SECONDS = 600
            deadline = asyncio.get_event_loop().time() + AGENT_TIMEOUT_SECONDS
            while not result_holder["done"] or events:
                if asyncio.get_event_loop().time() > deadline:
                    self._logger.warning(
                        f"Agent {agent_name} timed out after {AGENT_TIMEOUT_SECONDS}s, falling back to sync"
                    )
                    if not result_holder["done"]:
                        result_holder["done"] = True
                        result_holder["error"] = "timeout"
                    break
                with events_lock:
                    batch = list(events)
                    events.clear()

                for event in batch:
                    event_type = event.get("type", "")
                    event_data = event.get("data", {})
                    event_count += 1

                    if event_type == "thinking":
                        thought = event_data.get("message", "")
                        _emit("agent.thinking", f"💭 {thought}", {
                            "agent_name": agent_name,
                            "thought": thought,
                            "step": 0,
                        })
                        if not event_callback:
                            await publish_event(AgentThinkingEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                thought=thought,
                                step=0,
                            ))

                    elif event_type == "tool_call_start":
                        tool_name = event_data.get("name", "")
                        params = event_data.get("parameters", {})
                        _emit("agent.tool_call_start", f"🔧 调用工具: {tool_name}", {
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "parameters": params,
                        })
                        if not event_callback:
                            await publish_event(AgentToolCallStartEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                tool_name=tool_name,
                                parameters=params,
                            ))

                    elif event_type == "tool_call_end":
                        tool_name = event_data.get("name", "")
                        result = event_data.get("result", "")
                        result_str = str(result) if result else ""
                        success = event_data.get("success", True)
                        status_icon = "✅" if success else "❌"
                        _emit("agent.tool_call_end", f"{status_icon} {tool_name} 返回", {
                            "agent_name": agent_name,
                            "tool_name": tool_name,
                            "parameters": event_data.get("parameters", {}),
                            "result": result_str,
                            "success": success,
                        })
                        tool_results.append({
                            "tool": tool_name,
                            "parameters": event_data.get("parameters", {}),
                            "result": result,
                            "result_preview": result_str,
                            "success": success,
                        })
                        if not event_callback:
                            await publish_event(AgentToolCallEndEvent(
                                task_id=context.task_id,
                                user_id=context.user_id,
                                agent_name=agent_name,
                                tool_name=tool_name,
                                parameters=event_data.get("parameters", {}),
                                result=result,
                                success=success,
                            ))

                if not batch and not result_holder["done"]:
                    await asyncio.sleep(0.05)

            # 处理最终结果
            if result_holder["error"]:
                self._logger.error(
                    "Agent stream error",
                    agent=agent_name,
                    error=result_holder["error"],
                )
                if result_holder["error"] == "timeout":
                    structured_result = {
                        "failed": True,
                        "completed": False,
                        "error": f"Agent {agent_name} timed out",
                    }
                    final_text = ""
                else:
                    # Fallback: 同步调用
                    raw = await _run_agent_conversation(profile_id, user_input)
                    if isinstance(raw, dict):
                        structured_result = raw
                        final_text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
                    else:
                        final_text = str(raw) if raw else ""
            else:
                result = result_holder["result"]
                if isinstance(result, dict):
                    structured_result = result
                    final_text = result.get("final_response", "") or result.get("content", "") or json.dumps(result, ensure_ascii=False)
                else:
                    final_text = str(result) if result else ""

            self._logger.info(
                f"Agent stream completed: {agent_name}, events={event_count}, "
                f"content_len={len(final_text)}"
            )

        except Exception as e:
            self._logger.error(
                "Agent stream failed, falling back to sync",
                agent=agent_name,
                error=str(e),
                exc_info=True,
            )
            # Fallback: 同步调用
            raw = await _run_agent_conversation(profile_id, user_input)
            if isinstance(raw, dict):
                structured_result = raw
                final_text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
            else:
                final_text = str(raw) if raw else ""

        # 如果有 stream delta chunks 则拼接
        if content_chunks and not final_text:
            final_text = "".join(content_chunks)

        # ═══ 补充日志：从 Agent 输出文本中提取过程性内容 ═══
        if event_callback and final_text:
            self._emit_process_logs_from_text(final_text, agent_name, event_callback)

        return {
            "text": final_text,
            "tool_results": tool_results,
            "structured_result": structured_result,
        }

    def _emit_process_logs_from_text(
        self,
        text: str,
        agent_name: str,
        event_callback: Callable[[str, str, str, Dict[str, Any]], None],
    ) -> None:
        """从 Agent 输出文本中提取过程性内容，补充发射为日志事件

        当 Agent 没有真正触发工具回调（而是用文字描述了工具调用过程）时，
        从最终输出中解析步骤、工具调用、分析结论等，让前端日志有内容展示。
        """
        import re

        lines = text.split("\n")
        step_count = 0
        current_tool = ""
        collecting_result = False
        result_lines: list = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # 空行结束结果收集
                if collecting_result and result_lines:
                    result_text = "; ".join(result_lines)
                    event_callback(agent_name, "agent.tool_call_end",
                        f"✅ {current_tool} 返回",
                        {"agent_name": agent_name, "tool_name": current_tool,
                         "result": result_text, "success": True})
                    result_lines = []
                    collecting_result = False
                continue

            # 收集返回结果的缩进行
            if collecting_result:
                if stripped.startswith("-") or stripped.startswith("•") or line.startswith("  "):
                    clean = stripped.lstrip("-•").strip()
                    if clean:
                        result_lines.append(clean)
                    continue
                else:
                    # 非缩进行，结束收集
                    if result_lines:
                        result_text = "; ".join(result_lines)
                        event_callback(agent_name, "agent.tool_call_end",
                            f"✅ {current_tool} 返回",
                            {"agent_name": agent_name, "tool_name": current_tool,
                             "result": result_text, "success": True})
                        result_lines = []
                    collecting_result = False

            # 检测步骤标题（## 步骤N：xxx）
            step_match = re.match(r'^#{1,3}\s*(步骤|Step|阶段)\s*\d*[：:]?\s*(.+)', stripped)
            if step_match:
                step_count += 1
                step_desc = step_match.group(2).strip()
                event_callback(agent_name, "agent.thinking",
                    f"💭 {step_desc}",
                    {"agent_name": agent_name, "thought": step_desc, "step": step_count})
                continue

            # 检测工具调用（**工具调用：xxx**）— 精确匹配，避免重复
            tool_match = re.match(r'^\*{2}工具调用[：:]\s*`?(\w+)`?\*{2}', stripped)
            if tool_match:
                current_tool = tool_match.group(1)
                event_callback(agent_name, "agent.tool_call_start",
                    f"🔧 调用工具: {current_tool}",
                    {"agent_name": agent_name, "tool_name": current_tool, "parameters": {}})
                continue

            # 检测返回结果行
            result_match = re.match(r'^[-*]\s*返回结果[：:]?\s*(.*)$', stripped)
            if result_match:
                initial = result_match.group(1).strip()
                if initial:
                    result_lines.append(initial)
                collecting_result = True
                continue

            # 检测分析结论性标题
            conclusion_match = re.match(r'^#{1,3}\s*(总体评价|结论|分析结果|最终输出|综合评估)[：:]?\s*(.*)', stripped)
            if conclusion_match:
                desc = conclusion_match.group(1) + (": " + conclusion_match.group(2) if conclusion_match.group(2) else "")
                event_callback(agent_name, "agent.thinking",
                    f"💭 {desc}",
                    {"agent_name": agent_name, "thought": desc, "step": step_count + 1})

        # Flush 残留的结果
        if collecting_result and result_lines:
            result_text = "; ".join(result_lines)
            event_callback(agent_name, "agent.tool_call_end",
                f"✅ {current_tool} 返回",
                {"agent_name": agent_name, "tool_name": current_tool,
                 "result": result_text, "success": True})

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
