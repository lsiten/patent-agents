# -*- coding: utf-8 -*-
"""
专利申请工作流编排引擎
协调 CEO Agent 与各专业 Agent 完成端到端专利申请流程

架构：CEO Agent 通过 dispatch_specialist 工具动态调度各专业 Agent，
本引擎仅负责状态管理、进度追踪和前端 API 兼容。
"""
from pathlib import Path as _Path
import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, TypeVar
from urllib.parse import urlparse

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
from src.core.patent_compliance import (
    build_patent_text_from_draft,
    collect_high_priority_issues,
    normalize_claims_payload_linebreaks,
    sanitize_transcript_text,
    validate_claim_rules,
    validate_patent_manual_draft,
    validate_patent_document_structure,
)
try:
    from src.core.config import settings as _app_settings
except Exception:
    _app_settings = None


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

_CONTEXT_FIELD_TO_NODE = {
    "brainstorming_output": "brainstorm",
    "requirement_analysis": "requirement_analysis",
    "retrieval_report": "retrieval",
    "patent_draft": "writing",
    "review_report": "quality_review",
}

_WORKFLOW_STATE_TO_NODE = {
    "brainstorming": "brainstorm",
    "requirement_analysis": "requirement_analysis",
    "retrieval_analysis": "retrieval",
    "patent_writing": "writing",
    "quality_review": "quality_review",
    "awaiting_user_decision": "user_interrupt",
    "completed": "final_docx",
    "failed": "failed",
}

_AGUI_EVENT_MAP = {
    "agent.thinking": "TEXT_MESSAGE_CONTENT",
    "agent.content": "TEXT_MESSAGE_CONTENT",
    "agent.dispatch": "STATE_DELTA",
    "agent.tool_call_start": "TOOL_CALL_START",
    "agent.tool_call_delta": "TOOL_CALL_ARGS",
    "agent.tool_call_end": "TOOL_CALL_END",
    "workflow.phase_round.started": "PHASE_ROUND_STARTED",
    "workflow.phase_round.completed": "PHASE_ROUND_COMPLETED",
    "workflow.quality_gate.completed": "QUALITY_GATE_COMPLETED",
    "workflow.shared_facts.updated": "SHARED_FACTS_UPDATED",
    "workflow.human_input.requested": "HUMAN_INPUT_REQUESTED",
    "workflow.run.started": "RUN_STARTED",
    "workflow.run.finished": "RUN_FINISHED",
    "workflow.state.delta": "STATE_DELTA",
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


def _persist_workflow_checkpoint(task_id: str, checkpoint: dict) -> str:
    """Persist LangGraph-style workflow checkpoint snapshots.

    Phase artifacts are still stored in phase directories. This checkpoint file
    records graph state, route decisions, shared-facts versions and per-round
    references so UI reloads can reconstruct the workflow without guessing.
    """
    checkpoint_dir = _get_task_dir(task_id) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    reason = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(checkpoint.get("reason") or "checkpoint"))
    file_path = checkpoint_dir / f"{timestamp}_{reason[:80]}.json"
    payload = json.dumps(checkpoint, ensure_ascii=False, indent=2, default=str)
    file_path.write_text(payload, encoding="utf-8")
    latest_path = checkpoint_dir / "latest.json"
    latest_path.write_text(payload, encoding="utf-8")
    return str(file_path)


def _get_agent_factory():
    """返回 Agent 配置注册表实例，用于工作流阶段调用 Agent。
    通过 create_ai_agent(profile_id) 创建 AIAgent，然后调用 agent.run_conversation(prompt)。
    """
    from src.agents.agent_config import get_agent_config_registry
    return get_agent_config_registry()


async def _run_agent_conversation(
    profile_id: str,
    prompt: str,
    session_id: str | None = None,
    timeout_seconds: int = 600,
) -> str | Dict[str, Any]:
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
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return {
            "failed": True,
            "completed": False,
            "error": f"Agent {profile_id} timed out after {timeout_seconds}s",
        }
    
    if isinstance(result, dict):
        return result
    return str(result) if result else ""


async def _run_agent_conversation_with_timeout(
    profile_id: str,
    prompt: str,
    *,
    session_id: str | None = None,
    timeout_seconds: int = 600,
) -> str | Dict[str, Any]:
    """Call a Hermes Agent conversation with an explicit timeout.

    Tests often monkeypatch ``_run_agent_conversation`` with a minimal two-arg
    fake. Keep production behavior timeout-bound while letting those fakes stay
    focused on the Agent payload rather than the helper signature.
    """
    try:
        return await _run_agent_conversation(
            profile_id,
            prompt,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
    except TypeError as exc:
        message = str(exc)
        if "timeout_seconds" not in message and "session_id" not in message:
            raise
        if session_id is not None:
            try:
                return await _run_agent_conversation(profile_id, prompt, session_id)
            except TypeError as nested_exc:
                nested_message = str(nested_exc)
                if "positional" not in nested_message and "arguments" not in nested_message:
                    raise
        return await _run_agent_conversation(profile_id, prompt)

logger = get_logger("workflow_engine")
T = TypeVar("T", bound=BaseModel)

QUALITY_REMEDIATION_THRESHOLD = 0.9
QUALITY_REMEDIATION_SAFETY_LIMIT = 12
WRITER_INITIAL_TIMEOUT_SECONDS = 1800
WRITER_REVISION_TIMEOUT_SECONDS = 1200
WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS = 1200


def _configured_timeout_seconds(name: str, default: int) -> int:
    """Read optional workflow timeout config without making the engine depend on settings."""
    workflow = getattr(_app_settings, "workflow", None)
    value = None
    if workflow is not None:
        value = getattr(workflow, name, None)
    if value is None and _app_settings is not None:
        value = getattr(_app_settings, name, None)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return parsed if parsed > 0 else default
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

        # 专利标题（仅接收用户明确给出的发明名称或 Agent 产出的标题）
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
        self.shared_agent_context: Dict[str, Any] = {}
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
        if role == "user" and content:
            supplements = self.shared_agent_context.setdefault("user_supplements", [])
            if isinstance(supplements, list):
                supplements.append({
                    "content": content[:4000],
                    "timestamp": now.isoformat(),
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

        shared_context_text = self.get_shared_agent_context_text()
        if shared_context_text:
            parts.append("\n\n已确认/共享公共信息:\n" + shared_context_text)

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

    def get_shared_agent_context_text(self, limit: int = 10000) -> str:
        """Format confirmed facts and shared stage outputs for every Agent prompt."""
        if not self.shared_agent_context:
            return ""
        return json.dumps(self.shared_agent_context, ensure_ascii=False, indent=2)[:limit]

    def merge_shared_agent_context(self, key: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        old_value = self.shared_agent_context.get(key)
        if old_value == value:
            return
        previous_version = int(self.metadata.get("shared_facts_version") or 0)
        new_version = previous_version + 1
        self.shared_agent_context[key] = value
        self.shared_agent_context["_version"] = new_version
        history = self.metadata.setdefault("shared_facts_history", [])
        if isinstance(history, list):
            history.append({
                "version": new_version,
                "key": key,
                "timestamp": datetime.now().isoformat(),
                "previous_preview": json.dumps(old_value, ensure_ascii=False, default=str)[:1200]
                if old_value not in (None, "", [], {})
                else "",
                "value_preview": json.dumps(value, ensure_ascii=False, default=str)[:2000],
            })
            del history[:-100]
        self.metadata["shared_facts_version"] = new_version
        self.metadata["shared_agent_context"] = self.shared_agent_context
        self.updated_at = datetime.now()

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

_DOWNSTREAM_CONTEXT_FIELDS = {
    WorkflowState.REQUIREMENT_ANALYSIS: ("retrieval_report", "patent_draft", "review_report"),
    WorkflowState.RETRIEVAL_ANALYSIS: ("patent_draft", "review_report"),
    WorkflowState.PATENT_WRITING: ("review_report",),
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

    def _node_for_state(self, phase_state: WorkflowState | str) -> str:
        value = getattr(phase_state, "value", phase_state)
        return _WORKFLOW_STATE_TO_NODE.get(str(value), str(value))

    def _node_for_context_field(self, context_field: str) -> str:
        return _CONTEXT_FIELD_TO_NODE.get(context_field, context_field)

    def _phase_round_index(self, context: WorkflowContext, node: str) -> int:
        rounds = context.metadata.setdefault("phase_rounds", {})
        if not isinstance(rounds, dict):
            context.metadata["phase_rounds"] = {}
            rounds = context.metadata["phase_rounds"]
        node_rounds = rounds.setdefault(node, [])
        if not isinstance(node_rounds, list):
            rounds[node] = []
            node_rounds = rounds[node]
        return len(node_rounds) + 1

    def _summarize_for_checkpoint(self, data: Any, limit: int = 5000) -> Any:
        """Return a bounded JSON-safe summary for checkpoint files and events."""
        if data in (None, "", [], {}):
            return data
        try:
            clean = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        except Exception:
            clean = str(data)
        text = json.dumps(clean, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return clean
        return {
            "_truncated": True,
            "preview": text[:limit],
            "original_length": len(text),
        }

    def _build_workflow_snapshot(self, context: WorkflowContext) -> Dict[str, Any]:
        return {
            "task_id": context.task_id,
            "conversation_id": context.metadata.get("conversation_id"),
            "status": getattr(context.current_phase, "value", str(context.current_phase)),
            "current_node": self._node_for_state(context.current_phase),
            "current_round": context.iteration_count,
            "shared_facts_version": int(context.metadata.get("shared_facts_version") or 0),
            "shared_facts": self._summarize_for_checkpoint(context.shared_agent_context, limit=12000),
            "phase_rounds": self._summarize_for_checkpoint(
                context.metadata.get("phase_rounds", {}),
                limit=18000,
            ),
            "open_gaps": self._summarize_for_checkpoint(
                context.metadata.get("open_gaps")
                or context.shared_agent_context.get("unresolved_questions")
                or context.shared_agent_context.get("open_gaps")
                or [],
                limit=4000,
            ),
            "resolved_gaps": self._summarize_for_checkpoint(
                context.metadata.get("resolved_gaps")
                or context.shared_agent_context.get("resolved_questions")
                or [],
                limit=4000,
            ),
            "route_history": self._summarize_for_checkpoint(
                context.metadata.get("route_history", []),
                limit=8000,
            ),
            "interrupt": self._summarize_for_checkpoint(
                context.metadata.get("quality_remediation")
                or context.metadata.get("workflow_interrupt")
                or None,
                limit=4000,
            ),
        }

    def _persist_graph_checkpoint(
        self,
        context: WorkflowContext,
        reason: str,
        *,
        node: Optional[str] = None,
        round_index: Optional[int] = None,
        event: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        checkpoint = {
            "reason": reason,
            "node": node or self._node_for_state(context.current_phase),
            "round": round_index,
            "event": self._summarize_for_checkpoint(event or {}, limit=10000),
            "workflow_state": self._build_workflow_snapshot(context),
            "created_at": datetime.now().isoformat(),
        }
        try:
            path = _persist_workflow_checkpoint(context.task_id, checkpoint)
            context.metadata["latest_graph_checkpoint_path"] = path
            return path
        except Exception as exc:
            self._logger.warning(
                "Failed to persist workflow checkpoint",
                task_id=context.task_id,
                reason=reason,
                error=str(exc),
            )
            return None

    def _agui_metadata(
        self,
        context: WorkflowContext,
        agent_name: str,
        event_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(data or {})
        agui_type = _AGUI_EVENT_MAP.get(event_type, "STATE_DELTA")
        node = (
            payload.get("node")
            or payload.get("phase_node")
            or self._node_for_state(payload.get("phase") or context.current_phase)
        )
        call_name = (
            payload.get("tool_name")
            or payload.get("name")
            or payload.get("tool")
            or payload.get("skill")
            or event_type
        )
        call_id_src = f"{context.task_id}:{node}:{agent_name}:{call_name}:{payload.get('iteration_count') or payload.get('round') or ''}"
        call_id = hashlib.sha1(call_id_src.encode("utf-8")).hexdigest()[:16]
        payload.setdefault("agui_type", agui_type)
        payload.setdefault("run_id", context.task_id)
        payload.setdefault("message_id", f"{context.task_id}:{node}:{payload.get('round') or context.iteration_count}")
        payload.setdefault("parent_message_id", f"{context.task_id}:{node}")
        payload.setdefault("tool_call_id", call_id)
        payload.setdefault("state_delta", {
            "status": getattr(context.current_phase, "value", str(context.current_phase)),
            "current_node": node,
            "current_round": payload.get("round") or context.iteration_count,
            "shared_facts_version": int(context.metadata.get("shared_facts_version") or 0),
        })
        payload.setdefault("display_message", message)
        payload.setdefault("agent_name", agent_name)
        return payload

    def _record_phase_round(
        self,
        context: WorkflowContext,
        *,
        node: str,
        context_field: str,
        status: str,
        output: Any = None,
        duration_seconds: Optional[float] = None,
        issues: Optional[List[str]] = None,
        artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        rounds = context.metadata.setdefault("phase_rounds", {})
        if not isinstance(rounds, dict):
            context.metadata["phase_rounds"] = {}
            rounds = context.metadata["phase_rounds"]
        node_rounds = rounds.setdefault(node, [])
        if not isinstance(node_rounds, list):
            rounds[node] = []
            node_rounds = rounds[node]
        round_index = len(node_rounds) + 1
        record = {
            "node": node,
            "context_field": context_field,
            "round": round_index,
            "status": status,
            "duration_seconds": duration_seconds,
            "issues": issues or [],
            "artifact_path": artifact_path,
            "shared_facts_version": int(context.metadata.get("shared_facts_version") or 0),
            "output": self._summarize_for_checkpoint(output, limit=8000),
            "created_at": datetime.now().isoformat(),
        }
        node_rounds.append(record)
        self._persist_graph_checkpoint(
            context,
            f"{node}_round_{round_index}_{status}",
            node=node,
            round_index=round_index,
            event=record,
        )
        return record

    def _phase_contract_summary(self, context_field: str) -> Dict[str, Any]:
        contracts = {
            "requirement_analysis": {
                "node": "requirement_analysis",
                "inputs": [
                    "user_disclosure",
                    "brainstorm_output",
                    "shared_facts",
                    "retrieval_evidence",
                    "previous_feedback",
                ],
                "required_outputs": [
                    "tech_field",
                    "technical_problem",
                    "key_innovative_features",
                    "information_gaps",
                    "retrieval_feedback_review",
                    "shared_facts_delta",
                ],
                "gate": "must_resolve_before_writing 为空或可由检索继续解决",
            },
            "retrieval_report": {
                "node": "retrieval",
                "inputs": [
                    "requirement_gaps",
                    "shared_facts",
                    "previous_failed_queries",
                ],
                "required_outputs": [
                    "retrieval_strategy",
                    "retrieval_keywords",
                    "sources_used",
                    "retrieval_results",
                    "resolved_questions",
                    "unresolved_questions",
                ],
                "gate": "检索源不可用需记录并跳过；证据不足需调整检索式继续或明确转用户",
            },
            "patent_draft": {
                "node": "writing",
                "inputs": [
                    "shared_facts",
                    "requirement_analysis",
                    "retrieval_report",
                    "review_feedback",
                    "writing_rules",
                ],
                "required_outputs": [
                    "claims",
                    "description",
                    "abstract",
                    "drawings",
                    "docx_draft_path",
                ],
                "gate": "权利要求和说明书完整；附图由真实专利内容生成；DOCX 草稿可刷新",
            },
            "review_report": {
                "node": "quality_review",
                "inputs": [
                    "patent_draft",
                    "docx_draft",
                    "drawings",
                    "shared_facts",
                    "manual_rules",
                ],
                "required_outputs": [
                    "score",
                    "recommendation",
                    "issues",
                    "root_cause",
                    "route_to",
                ],
                "gate": "score >= 90 且无 high/critical 阻塞问题",
            },
        }
        return contracts.get(context_field, {"node": context_field})

    def _invalidate_downstream_outputs(
        self,
        context: WorkflowContext,
        phase_state: WorkflowState,
        reason: str,
        preserve_fields: Optional[List[str]] = None,
    ) -> None:
        """Clear current downstream artifacts after an upstream phase changes.

        Phase history is preserved for per-round UI tabs. Only current context
        fields are cleared, so an older draft/review cannot be treated as the
        latest valid output after requirement or retrieval has changed.
        """
        fields = _DOWNSTREAM_CONTEXT_FIELDS.get(phase_state, ())
        if not fields:
            return
        preserved = set(preserve_fields or [])
        invalidated: List[str] = []
        for field in fields:
            if field in preserved:
                continue
            if getattr(context, field, None):
                setattr(context, field, {})
                invalidated.append(field)
        if invalidated:
            context.metadata["stale_downstream_outputs"] = {
                "phase": phase_state.value,
                "fields": invalidated,
                "reason": reason,
                "invalidated_at": datetime.now().isoformat(),
            }

    def _preserve_downstream_fields_after_phase(
        self,
        phase_state: WorkflowState,
        phase_output: Any,
    ) -> List[str]:
        """Return downstream artifacts that remain valid after an upstream round.

        Requirement analysis has two modes in the current loop:
        1. initial analysis or substantive update before retrieval, which must
           invalidate old retrieval/writing/review artifacts;
        2. post-retrieval review confirming gaps are closed, which must preserve
           the retrieval report that was just reviewed and only invalidate stale
           draft/review artifacts.
        """
        if phase_state != WorkflowState.REQUIREMENT_ANALYSIS or not isinstance(phase_output, dict):
            return []

        retrieval_review = phase_output.get("retrieval_feedback_review")
        if isinstance(retrieval_review, dict) and self._requirement_review_allows_drafting(
            retrieval_review
        ):
            return ["retrieval_report"]

        if self._requirement_review_allows_drafting(phase_output):
            return ["retrieval_report"]

        return []

    def _update_shared_context_from_phase(
        self,
        context: WorkflowContext,
        context_field: str,
        data: Any,
    ) -> None:
        """Share confirmed phase facts with downstream Agents without hiding full artifacts."""
        if not isinstance(data, dict) or not data:
            return
        phase_key = {
            "requirement_analysis": "latest_requirement_analysis",
            "retrieval_report": "latest_retrieval_report",
            "patent_draft": "latest_patent_draft_summary",
            "review_report": "latest_quality_review",
        }.get(context_field, context_field)
        compact = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        if context_field == "requirement_analysis":
            compact = self._attach_confirmed_preflight_to_requirement(context, compact)
        if context_field == "patent_draft":
            compact = self._build_quality_review_draft_summary(data)
        context.merge_shared_agent_context(phase_key, compact)

    def _attach_confirmed_preflight_to_requirement(
        self,
        context: WorkflowContext,
        requirement: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensure requirement facts include the user-confirmed preflight package.

        Requirement analysis is allowed to focus on technical gaps, but downstream
        Agents and the preview UI still need the confirmed patent name/type and
        public facts in the same artifact instead of inferring them from chat.
        """
        if not isinstance(requirement, dict):
            return requirement
        enriched = dict(requirement)
        confirmed = (
            context.metadata.get("confirmed_preflight")
            or context.shared_agent_context.get("confirmed_preflight")
            or {}
        )
        if not isinstance(confirmed, dict):
            confirmed = {}

        patent_title = str(
            enriched.get("patent_title")
            or enriched.get("title")
            or confirmed.get("patent_title")
            or context.title
            or ""
        ).strip()
        if patent_title:
            enriched.setdefault("patent_title", patent_title)
            enriched.setdefault("title", patent_title)

        patent_type = str(
            enriched.get("patent_type")
            or confirmed.get("patent_type")
            or confirmed.get("专利类型")
            or ""
        ).strip()
        if patent_type and "patent_type" not in enriched:
            enriched["patent_type"] = patent_type

        if "confirmed_facts" not in enriched:
            facts = {
                k: v
                for k, v in confirmed.items()
                if k
                in {
                    "patent_title",
                    "patent_type",
                    "public_status",
                    "claim_mainline",
                    "technical_solution",
                    "drawing_plan",
                    "protection_focus",
                }
                and v not in (None, "", [], {})
            }
            if facts:
                enriched["confirmed_facts"] = facts
        return enriched

    def create_workflow(
        self,
        task_id: str,
        user_id: str,
        description: str,
        patent_type_preference: Optional[str] = None,
        skip_phases: Optional[List[WorkflowState]] = None,
        target_country: str = "中国",
        confirmed_preflight: Optional[Dict[str, Any]] = None,
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
        if confirmed_preflight:
            context.title = str(confirmed_preflight.get("patent_title") or context.title)
            context.merge_shared_agent_context("confirmed_preflight", confirmed_preflight)
            context.metadata["confirmed_preflight"] = confirmed_preflight
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
        result = sanitize_transcript_text(description)
        return str(result.get("cleaned_text") or description).strip()

    @staticmethod
    def _extract_title(description: str) -> str:
        """Extract only an explicitly provided invention title.

        Meeting transcripts often begin with casual speech. Guessing a title from
        the first sentence leaks disclosure artifacts into the patent document, so
        missing titles must remain empty and be handled by the drafting/review loop.
        """
        if not description:
            return ""
        text = PatentWorkflowEngine._sanitize_disclosure_text(description)
        explicit_patterns = [
            r"(?:^|\n)\s*(?:发明名称|专利名称|申请名称|技术名称)\s*[:：]\s*(.+)",
            r"(?:^|\n)\s*名称\s*[:：]\s*(.+)",
        ]
        for pattern in explicit_patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            title = str(match.group(1) or "").strip()
            title = re.split(r"[\n。；;]", title, maxsplit=1)[0].strip(" ：:，,。")
            title = re.sub(r"^(一种|一项)?待命名[:：]?", "", title).strip()
            if 2 <= len(title) <= 60 and not re.search(r"\d{1,2}:\d{2}|\d{2}:\d{2}:\d{2}", title):
                return title
        return ""

    def get_workflow(self, task_id: str) -> Optional[WorkflowContext]:
        """获取工作流上下文"""
        return self._running_workflows.get(task_id)

    def list_workflows(self) -> List[WorkflowContext]:
        """列出所有工作流上下文"""
        return list(self._running_workflows.values())

    async def _persist_loop_and_sediment_skills(
        self,
        context: WorkflowContext,
        terminal_state: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Persist loop state and write per-agent Hermes skills.

        Skill sedimentation is an auxiliary learning step. It must never mask the
        workflow's real terminal result, so all exceptions are logged and swallowed.
        """
        try:
            from src.core.agent_loop import persist_patent_loop_snapshot
            from src.agents.hermes.skill_learning import sediment_workflow_skills

            snapshot = persist_patent_loop_snapshot(context, terminal_state)
            touched = sediment_workflow_skills(context, snapshot)
            context.metadata["loop_snapshot_path"] = snapshot.get("path", "")
            context.metadata["sedimented_skills"] = touched
            if event_callback:
                display_names = {
                    "ceo": "CEO Agent",
                    "requirement_analyst": "需求分析师",
                    "retrieval_analyst": "检索分析师",
                    "patent_writer": "专利撰写 Agent",
                    "quality_reviewer": "质量审查 Agent",
                }
                for item in touched:
                    agent_profile = item.get("agent_profile", "")
                    agent_name = display_names.get(agent_profile, agent_profile or "Agent")
                    event_callback(
                        agent_name,
                        "agent.skill_sedimented",
                        f"🧠 已沉淀技能：{item.get('skill', '')}",
                        {
                            "agent_name": agent_name,
                            "content": item.get("skill_path", ""),
                            "message": f"已沉淀技能：{item.get('skill', '')}",
                            "skill": item.get("skill", ""),
                            "skill_path": item.get("skill_path", ""),
                            "log_path": item.get("log_path", ""),
                        },
                    )
                event_callback(
                    "CEO Agent",
                    "agent.content",
                    f"🧠 已完成自动技能沉淀：{len(touched)} 个 Agent profile",
                    {
                        "agent_name": "CEO Agent",
                        "content": "Hermes profile-local skills updated",
                        "loop_snapshot_path": snapshot.get("path", ""),
                        "skills": touched,
                    },
                )
            return snapshot
        except Exception as exc:
            self._logger.warning(
                f"Failed to persist loop snapshot or sediment skills: {exc}",
                task_id=context.task_id,
                exc_info=True,
            )
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.thinking",
                    "⚠️ 自动技能沉淀失败，不影响当前流程状态",
                    {
                        "agent_name": "CEO Agent",
                        "thought": "skill_sedimentation_failed",
                        "error": str(exc),
                    },
                )
            return {}

    async def execute_full_workflow(
        self,
        context: WorkflowContext,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        agent_event_callback: Optional[Callable[[Dict[str, Any]], None | Awaitable[None]]] = None,
        checkpoint_callback: Optional[Callable[[WorkflowContext, str], None | Awaitable[None]]] = None,
        force_start_from: Optional[WorkflowState] = None,
    ) -> WorkflowContext:
        """
        执行完整工作流 — 顺序调用各专业 Agent

        每个阶段由对应的专业 Agent 直接执行，确保各阶段有实际输出。
        patent_writer 使用分段生成策略（权利要求+说明书+摘要）。
        """
        self._logger.info("Starting workflow", task_id=context.task_id)
        original_event_callback = event_callback

        def emit_workflow_event(
            agent_name: str,
            event_type: str,
            message: str,
            data: Optional[Dict[str, Any]] = None,
        ) -> None:
            enriched = self._agui_metadata(context, agent_name, event_type, message, data or {})
            if original_event_callback:
                original_event_callback(agent_name, event_type, message, enriched)
            if event_type in {
                "workflow.phase_round.started",
                "workflow.phase_round.completed",
                "workflow.quality_gate.completed",
                "workflow.shared_facts.updated",
                "workflow.human_input.requested",
                "workflow.run.started",
                "workflow.run.finished",
            }:
                self._persist_graph_checkpoint(
                    context,
                    event_type,
                    node=enriched.get("state_delta", {}).get("current_node"),
                    round_index=enriched.get("state_delta", {}).get("current_round"),
                    event={
                        "agent_name": agent_name,
                        "event_type": event_type,
                        "message": message,
                        "data": enriched,
                    },
                )

        event_callback = emit_workflow_event

        if event_callback:
            event_callback(
                "CEO Agent",
                "workflow.run.started",
                "工作流开始执行",
                {"phase": getattr(context.current_phase, "value", str(context.current_phase))},
            )

        async def emit_agent_work_event(event: Dict[str, Any]) -> None:
            if agent_event_callback is None:
                return
            event.setdefault("task_id", context.task_id)
            event.setdefault("timestamp", datetime.now().isoformat())
            result = agent_event_callback(event)
            if asyncio.iscoroutine(result):
                await result

        async def checkpoint(reason: str) -> None:
            context.metadata["latest_checkpoint"] = {
                "reason": reason,
                "phase": str(getattr(context.current_phase, "value", context.current_phase)),
                "iteration_count": context.iteration_count,
                "timestamp": datetime.now().isoformat(),
            }
            self._persist_graph_checkpoint(context, reason)
            if checkpoint_callback is None:
                return
            result = checkpoint_callback(context, reason)
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
            if force_start_from:
                start_index = next(
                    (
                        index
                        for index, (_, _, _, phase_state, _) in enumerate(phases)
                        if phase_state == force_start_from
                    ),
                    0,
                )
                phases = phases[start_index:]
                context.current_phase = WorkflowState.ITERATION
                context.iteration_count += 1

            for agent_id, profile_id, context_field, phase_state, phase_enum in phases:
                if context.metadata.get("cancel_requested") or context.current_phase == WorkflowState.CANCELLED:
                    raise asyncio.CancelledError()
                if phase_state == WorkflowState.PATENT_WRITING:
                    ready_to_write = await self._ensure_prewriting_ready(
                        context,
                        event_callback=event_callback,
                        phase_callback=phase_callback,
                        checkpoint_callback=checkpoint_callback,
                    )
                    if not ready_to_write:
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        await checkpoint("prewriting_gate_waiting")
                        return context
                phase_started_at = time.perf_counter()
                context.current_phase = phase_state
                await self._publish_progress_event(context, phase_state, "running")
                await checkpoint(f"{phase_state.value}_running")
                phase_node = self._node_for_context_field(context_field)
                phase_round = self._phase_round_index(context, phase_node)

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
                if event_callback:
                    event_callback(
                        agent_display_name,
                        "workflow.phase_round.started",
                        f"{agent_display_name} 第{phase_round}轮开始",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "context_field": context_field,
                            "input_contract": self._phase_contract_summary(context_field),
                        },
                    )
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

                        # patent_writer must use the sectioned writer path even when Hermes
                        # streaming is available; otherwise one long turn hides writing progress
                        # and delays persisted stage output until the whole draft finishes.
                        if agent_id == "patent_writer":
                            # 发射分段生成进度事件
                            if event_callback:
                                event_callback(agent_display_name, "agent.thinking",
                                    "💭 开始分段生成专利文件（权利要求 → 说明书 → 摘要）",
                                    {"agent_name": agent_display_name, "thought": "分段生成专利文件", "step": 1})
                            context_data = await asyncio.wait_for(
                                self._generate_patent_in_sections(
                                    service,
                                    profile_id,
                                    task_desc,
                                    context,
                                    event_callback=event_callback,
                                ),
                                timeout=_configured_timeout_seconds(
                                    "writer_initial_timeout_seconds",
                                    WRITER_INITIAL_TIMEOUT_SECONDS,
                                ),
                            )
                            if isinstance(context_data, dict):
                                context_data = await self._ensure_required_patent_drawings(
                                    context,
                                    context_data,
                                    event_callback=event_callback,
                                )
                                context_data = self._apply_patent_manual_normalization(
                                    context_data,
                                    context_title=context.title,
                                )
                                context_data = await self._refresh_working_draft_docx(
                                    context,
                                    context_data,
                                    checkpoint="分段撰写",
                                    event_callback=event_callback,
                                )
                                context_data = self._clear_stale_writer_failure_if_reviewable(
                                    context_data
                                )
                                context_data["_writer_postprocessed"] = True
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
                        contract_issues = self._validate_phase_contract(
                            context_field,
                            context_data,
                        )
                        if contract_issues:
                            last_error = RuntimeError("；".join(contract_issues[:5]))
                            if attempt >= max_retries:
                                context_data = self._build_phase_contract_error(
                                    context_field,
                                    context_data,
                                    contract_issues,
                                )
                                break
                            raise last_error
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
                previous_shared_facts_version = int(context.metadata.get("shared_facts_version") or 0)
                self._update_shared_context_from_phase(context, context_field, context_data)
                if event_callback and int(context.metadata.get("shared_facts_version") or 0) != previous_shared_facts_version:
                    event_callback(
                        agent_display_name,
                        "workflow.shared_facts.updated",
                        f"{agent_display_name} 更新了公共事实",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "shared_facts_version": context.metadata.get("shared_facts_version"),
                            "shared_facts_delta": self._summarize_for_checkpoint(
                                context_data.get("shared_facts_delta") if isinstance(context_data, dict) else {},
                                limit=3000,
                            ),
                        },
                    )
                if (
                    agent_id == "patent_writer"
                    and isinstance(context_data, dict)
                    and context_data.get("_writer_postprocessed") is not True
                ):
                    context_data = await self._ensure_required_patent_drawings(
                        context,
                        context_data,
                        event_callback=event_callback,
                    )
                    context_data = self._apply_patent_manual_normalization(
                        context_data,
                        context_title=context.title,
                    )
                    context_data = await self._refresh_working_draft_docx(
                        context,
                        context_data,
                        checkpoint="附图补齐",
                        event_callback=event_callback,
                    )
                    context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    setattr(context, context_field, context_data)
                    previous_shared_facts_version = int(context.metadata.get("shared_facts_version") or 0)
                    self._update_shared_context_from_phase(context, context_field, context_data)
                    if event_callback and int(context.metadata.get("shared_facts_version") or 0) != previous_shared_facts_version:
                        event_callback(
                            agent_display_name,
                            "workflow.shared_facts.updated",
                            f"{agent_display_name} 更新了公共事实",
                            {
                                "phase": phase_state.value,
                                "phase_node": phase_node,
                                "round": phase_round,
                                "shared_facts_version": context.metadata.get("shared_facts_version"),
                                "shared_facts_delta": self._summarize_for_checkpoint(
                                    context_data.get("shared_facts_delta") if isinstance(context_data, dict) else {},
                                    limit=3000,
                                ),
                            },
                        )

                agent_failed = (
                    isinstance(context_data, dict)
                    and context_data.get("_agent_failed") is True
                )
                agent_error = ""
                if agent_failed:
                    agent_error = str(
                        context_data.get("_agent_error") or "Agent execution failed"
                    )[:500]

                phase_duration = time.perf_counter() - phase_started_at
                if isinstance(context_data, dict):
                    context_data.setdefault("_phase_duration_seconds", phase_duration)

                # 持久化阶段结果到对应子目录
                saved_path = None
                try:
                    saved_path = _persist_phase_result(
                        context.task_id, context_field,
                        context_data if isinstance(context_data, dict) else {"output": str(context_data)},
                    )
                    self._logger.info(f"Phase result persisted: {saved_path}")
                except Exception as e:
                    self._logger.warning(f"Failed to persist phase result: {e}")

                if agent_failed:
                    round_record = self._record_phase_round(
                        context,
                        node=phase_node,
                        context_field=context_field,
                        status="failed",
                        output=context_data,
                        duration_seconds=phase_duration,
                        issues=[agent_error] if agent_error else [],
                        artifact_path=saved_path,
                    )
                    if event_callback:
                        event_callback(
                            agent_display_name,
                            "workflow.phase_round.completed",
                            f"{agent_display_name} 第{phase_round}轮失败",
                            {
                                "phase": phase_state.value,
                                "phase_node": phase_node,
                                "round": phase_round,
                                "round_record": round_record,
                                "issues": [agent_error] if agent_error else [],
                            },
                        )
                    context.add_phase_result(PhaseResult(
                        phase=phase_enum,
                        success=False,
                        duration_seconds=phase_duration,
                        output=context_data,
                        issues=[agent_error] if agent_error else [],
                    ))
                    await self._publish_progress_event(context, phase_state, "failed")
                    context.current_phase = WorkflowState.FAILED
                    await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                    await checkpoint(f"{phase_state.value}_failed")
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
                    await self._persist_loop_and_sediment_skills(
                        context,
                        "failed",
                        event_callback,
                    )
                    return context

                self._invalidate_downstream_outputs(
                    context,
                    phase_state,
                    reason="upstream_phase_completed",
                    preserve_fields=self._preserve_downstream_fields_after_phase(
                        phase_state,
                        context_data,
                    ),
                )

                # 记录阶段完成
                context.add_phase_result(PhaseResult(
                    phase=phase_enum,
                    success=True,
                    duration_seconds=phase_duration,
                    output=context_data if isinstance(context_data, dict) else {},
                ))
                round_record = self._record_phase_round(
                    context,
                    node=phase_node,
                    context_field=context_field,
                    status="completed",
                    output=context_data,
                    duration_seconds=phase_duration,
                    artifact_path=saved_path,
                )
                if event_callback:
                    event_callback(
                        agent_display_name,
                        "workflow.phase_round.completed",
                        f"{agent_display_name} 第{phase_round}轮完成",
                        {
                            "phase": phase_state.value,
                            "phase_node": phase_node,
                            "round": phase_round,
                            "round_record": round_record,
                            "output_contract": self._phase_contract_summary(context_field),
                        },
                    )
                await self._publish_progress_event(context, phase_state, "completed")
                await checkpoint(f"{phase_state.value}_completed")
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
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.quality_gate.completed",
                            f"质量门未通过，路由：{remediation_path}",
                            {
                                "phase": "quality_review",
                                "phase_node": "quality_review",
                                "round": context.iteration_count,
                                "passed": False,
                                "score": context.latest_review_score,
                                "issues": review_issues,
                                "route_to": remediation_path,
                                "review_report": self._summarize_for_checkpoint(
                                    context.review_report,
                                    limit=8000,
                                ),
                            },
                        )

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

                    # max_iterations 只是软提示阈值；质量未达标时默认继续自动修复。
                    if context.iteration_count >= max_iterations:
                        self._logger.warning(
                            f"Automatic remediation exceeded soft threshold ({max_iterations}); continuing",
                            task_id=context.task_id,
                        )
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                f"⚠️ 已连续自动修正 {max_iterations} 轮仍未通过质量检测，将继续自动修复并复审",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "auto_remediation_soft_threshold_reached",
                                    "iteration_count": context.iteration_count,
                                    "max_iterations": max_iterations,
                                },
                            )

                    if context.iteration_count >= safety_limit:
                        self._logger.error(
                            f"Automatic remediation reached safety limit ({safety_limit})",
                            task_id=context.task_id,
                        )
                        remediation_path = "TERMINAL_FAILURE"

                    if remediation_path == "TERMINAL_FAILURE":
                        break

                    if remediation_path == "NEEDS_USER_INPUT":
                        self._enter_quality_remediation_hold(context, context.review_report, remediation_path)
                        context.current_phase = WorkflowState.AWAITING_USER_DECISION
                        if event_callback:
                            remediation = context.metadata.get("quality_remediation", {})
                            missing_information = remediation.get("missing_information", [])
                            detail = "；".join(str(item) for item in missing_information) if missing_information else "缺少额外信息"

                            event_callback(
                                "CEO Agent",
                                "workflow.human_input.requested",
                                f"需要用户补充：{detail}",
                                {
                                    "phase": "quality_review",
                                    "phase_node": "user_interrupt",
                                    "missing_information": missing_information,
                                    "resume_phase": remediation.get("resume_phase"),
                                    "interrupt_type": "quality_remediation",
                                },
                            )
                            event_callback(
                                "CEO Agent",
                                "agent.content",
                                f"⏸️ 质量审查指出存在必须由用户确认的信息，流程已暂停：{detail}",
                                {
                                    "agent_name": "CEO Agent",
                                    "phase": "quality_review",
                                    "content": detail,
                                    "missing_information": missing_information,
                                },
                            )
                        await self._publish_progress_event(
                            context,
                            WorkflowState.AWAITING_USER_DECISION,
                            "waiting",
                        )
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        return context

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
                            phase_callback=phase_callback,
                            checkpoint_callback=checkpoint_callback,
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
                            phase_callback=phase_callback,
                            checkpoint_callback=checkpoint_callback,
                        )

                    ready_to_write = await self._ensure_prewriting_ready(
                        context,
                        event_callback=event_callback,
                        phase_callback=phase_callback,
                        checkpoint_callback=checkpoint_callback,
                    )
                    if not ready_to_write:
                        await self._persist_loop_and_sediment_skills(
                            context,
                            "awaiting_user_decision",
                            event_callback,
                        )
                        await checkpoint("quality_remediation_waiting")
                        return context

                    # ── 修正撰写 ──
                    revision_started_at = time.perf_counter()
                    context.current_phase = WorkflowState.PATENT_WRITING
                    await self._publish_progress_event(context, WorkflowState.PATENT_WRITING, "running")

                    review_requires_drawing_changes = self._review_requires_drawing_changes(
                        context.review_report
                    )
                    revision_prompt = self._build_revision_prompt(
                        context,
                        review_issues,
                        allow_drawing_generation=review_requires_drawing_changes,
                    )

                    if event_callback:
                        event_callback("CEO Agent", "agent.dispatch",
                            f"🎯 调度 → 专利撰写 Agent（修正迭代第{context.iteration_count}轮）",
                            {"from_agent": "CEO Agent", "to_agent": "专利撰写 Agent", "task_description": revision_prompt[:300]})

                    try:
                        context_data = await asyncio.wait_for(
                            self._generate_patent_in_sections(
                                service,
                                "patent.writer.v1",
                                revision_prompt,
                                context,
                                event_callback=event_callback,
                                allow_drawing_generation=review_requires_drawing_changes,
                            ),
                            timeout=int(
                                context.metadata.get(
                                    "writer_revision_timeout_seconds",
                                    WRITER_REVISION_TIMEOUT_SECONDS,
                                )
                                or WRITER_REVISION_TIMEOUT_SECONDS
                            ),
                        )
                        agent_text = json.dumps(context_data, ensure_ascii=False)[:500]
                        agent_tool_results = []
                    except asyncio.TimeoutError:
                        timeout_seconds = int(
                            context.metadata.get(
                                "writer_revision_timeout_seconds",
                                WRITER_REVISION_TIMEOUT_SECONDS,
                            )
                            or WRITER_REVISION_TIMEOUT_SECONDS
                        )
                        self._logger.warning(
                            f"Patent writer revision timed out after {timeout_seconds}s; marking draft failed",
                            task_id=context.task_id,
                        )
                        agent_text = ""
                        agent_tool_results = []
                        context_data = {
                            "_agent_failed": True,
                            "_incomplete_output": True,
                            "_agent_error": (
                                f"专利撰写 Agent 修正第{context.iteration_count}轮超过 "
                                f"{timeout_seconds}s 未完成，不能继续生成最终DOCX。"
                            ),
                            "claims": {},
                            "description": {},
                            "abstract": "",
                            "drawings": [],
                            "docx_path": "",
                        }
                    except Exception as exc:
                        self._logger.warning(
                            f"Patent writer revision failed; marking draft for Agent-led retry: {exc}",
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
                    if not isinstance(context_data, dict):
                        context_data = {
                            "_agent_failed": True,
                            "_incomplete_output": True,
                            "_agent_error": "专利撰写 Agent 修正结果不是结构化对象。",
                            "claims": {},
                            "description": {},
                            "abstract": "",
                            "drawings": [],
                            "docx_path": "",
                        }
                    context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                    contract_issues = self._validate_phase_contract("patent_draft", context_data)
                    if contract_issues:
                        context_data = self._build_phase_contract_error(
                            "patent_draft",
                            context_data,
                            contract_issues,
                        )
                    if isinstance(context_data, dict) and context_data.get("_agent_failed") is not True:
                        context_data = self._apply_review_suggestions_to_draft(
                            context,
                            context_data,
                            review_issues,
                            event_callback=event_callback,
                        )
                        context_data = self._merge_reusable_revision_drawings(
                            context,
                            context_data,
                            review_issues,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        context_data = await self._ensure_required_patent_drawings(
                            context,
                            context_data,
                            event_callback=event_callback,
                        )
                        context_data = self._apply_patent_manual_normalization(
                            context_data,
                            context_title=context.title,
                        )
                        context_data = await self._refresh_working_draft_docx(
                            context,
                            context_data,
                            checkpoint=f"修正第{context.iteration_count}轮",
                            event_callback=event_callback,
                        )
                        context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                        contract_issues = self._validate_phase_contract("patent_draft", context_data)
                        if contract_issues:
                            context_data = self._build_phase_contract_error(
                                "patent_draft",
                                context_data,
                                contract_issues,
                            )
                    revision_duration = time.perf_counter() - revision_started_at
                    if isinstance(context_data, dict):
                        context_data.setdefault("_phase_duration_seconds", revision_duration)
                    writer_failed = (
                        isinstance(context_data, dict)
                        and context_data.get("_agent_failed") is True
                    )
                    if not writer_failed:
                        context.patent_draft = context_data
                        self._update_shared_context_from_phase(context, "patent_draft", context_data)
                        # 持久化修正后的撰写结果。失败/超时输出不能覆盖上一轮有效草稿。
                        try:
                            _persist_phase_result(context.task_id, "patent_draft", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                        except Exception:
                            pass
                    else:
                        context.metadata["last_writer_failure"] = {
                            "iteration_count": context.iteration_count,
                            "error": str(context_data.get("_agent_error") or "专利撰写 Agent 修正失败"),
                            "duration_seconds": revision_duration,
                        }
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.WRITING,
                        success=not writer_failed,
                        duration_seconds=revision_duration,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if writer_failed else [],
                    ))
                    await self._publish_progress_event(
                        context,
                        WorkflowState.PATENT_WRITING,
                        "failed" if writer_failed else "completed",
                    )
                    if phase_callback:
                        last_result = context.phase_history[-1]
                        if asyncio.iscoroutinefunction(phase_callback):
                            await phase_callback(WorkflowState.PATENT_WRITING, last_result)
                        else:
                            phase_callback(WorkflowState.PATENT_WRITING, last_result)
                    await checkpoint(
                        f"quality_revision_writing_round_{context.iteration_count}_"
                        f"{'failed' if writer_failed else 'completed'}"
                    )
                    if writer_failed:
                        if event_callback:
                            event_callback(
                                "CEO Agent",
                                "agent.thinking",
                                "⚠️ 专利撰写 Agent 本轮修正未完成，已保留上一轮有效草稿，继续调度撰写 Agent 基于原审查意见修复",
                                {
                                    "agent_name": "CEO Agent",
                                    "thought": "writer_revision_failed_preserve_previous_draft",
                                    "iteration_count": context.iteration_count,
                                },
                            )
                        continue

                    # ── 重新审查 ──
                    review_started_at = time.perf_counter()
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
                    contract_issues = self._validate_phase_contract("review_report", context_data)
                    if contract_issues:
                        context_data = self._build_phase_contract_error(
                            "review_report",
                            context_data,
                            contract_issues,
                        )
                    review_duration = time.perf_counter() - review_started_at
                    if isinstance(context_data, dict):
                        context_data.setdefault("_phase_duration_seconds", review_duration)
                    context.review_report = context_data
                    self._update_shared_context_from_phase(context, "review_report", context_data)
                    # 持久化审查结果
                    try:
                        _persist_phase_result(context.task_id, "review_report", context_data if isinstance(context_data, dict) else {"output": str(context_data)})
                    except Exception:
                        pass
                    context.add_phase_result(PhaseResult(
                        phase=WorkflowPhase.REVIEW,
                        success=not (isinstance(context_data, dict) and context_data.get("_agent_failed") is True),
                        duration_seconds=review_duration,
                        output=context_data if isinstance(context_data, dict) else {},
                        issues=[
                            str(context_data.get("_agent_error", ""))
                        ] if isinstance(context_data, dict) and context_data.get("_agent_failed") is True else [],
                    ))
                    await self._publish_progress_event(context, WorkflowState.QUALITY_REVIEW, "completed")
                    if phase_callback:
                        last_result = context.phase_history[-1]
                        if asyncio.iscoroutinefunction(phase_callback):
                            await phase_callback(WorkflowState.QUALITY_REVIEW, last_result)
                        else:
                            phase_callback(WorkflowState.QUALITY_REVIEW, last_result)
                    await checkpoint(f"quality_review_round_{context.iteration_count + 1}_completed")

                # 检查审查是否通过
                needs_remediation = self._needs_quality_remediation(context.review_report)
                context.latest_review_score = self._extract_normalized_review_score(context.review_report) or 0.0
                if not needs_remediation:
                    review_passed = True
                    context.metadata.pop("quality_remediation", None)
                    self._logger.info("Quality review passed", task_id=context.task_id)
                    if event_callback:
                        event_callback(
                            "质量审查 Agent",
                            "workflow.quality_gate.completed",
                            "质量门通过",
                            {
                                "phase": "quality_review",
                                "phase_node": "quality_review",
                                "round": context.iteration_count + 1,
                                "passed": True,
                                "score": context.latest_review_score,
                                "route_to": "complete",
                                "review_report": self._summarize_for_checkpoint(
                                    context.review_report,
                                    limit=8000,
                                ),
                            },
                        )
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
                await self._persist_loop_and_sediment_skills(
                    context,
                    "awaiting_user_decision",
                    event_callback,
                )
                await checkpoint("awaiting_user_decision_before_final_docx")
                return context

            if self._has_unresolved_critical_issues(context):
                self._logger.error(
                    "Workflow cannot complete: unresolved critical issues remain "
                    "(patent_draft incomplete OR review has critical issues). "
                    f"task_id={context.task_id}, iteration_count={context.iteration_count}",
                    task_id=context.task_id,
                )
                
                # 详细分析失败原因
                failure_details = self._analyze_workflow_failure(context)
                
                if event_callback:
                    # 发布主错误信息
                    msg = f"❌ 流程未能完成: {failure_details['main_reason']}"
                    event_callback("CEO Agent", "agent.thinking", msg, {
                        "agent_name": "CEO Agent",
                        "thought": "workflow_failed_unresolved_critical_issues",
                        "failure_phase": failure_details["phase"],
                        "failure_reason": failure_details["main_reason"],
                    })
                    
                    # 发布详细的失败分析
                    if failure_details["phase"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"📍 失败阶段: {failure_details['phase_display']}", {
                                "agent_name": "CEO Agent",
                                "thought": "failure_phase",
                                "phase": failure_details["phase"],
                                "phase_display": failure_details["phase_display"],
                            })
                    
                    # 发布具体问题列表
                    for issue in failure_details["issues"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"⚠️ {issue['message']}", {
                                "agent_name": "CEO Agent",
                                "thought": "failure_issue",
                                "issue_type": issue["type"],
                                "severity": issue["severity"],
                            })
                    
                    # 发布优化建议
                    event_callback("CEO Agent", "agent.thinking", 
                        "💡 优化建议:", {
                            "agent_name": "CEO Agent",
                            "thought": "optimization_tips_start",
                        })
                    for tip in failure_details["suggestions"]:
                        event_callback("CEO Agent", "agent.thinking", 
                            f"   • {tip}", {
                                "agent_name": "CEO Agent",
                                "thought": "optimization_tip",
                            })
                
                context.current_phase = WorkflowState.FAILED
                await self._publish_progress_event(context, WorkflowState.FAILED, "failed")
                
                # 发布详细的失败事件
                await emit_agent_work_event({
                    "event_type": "workflow.failed",
                    "task_id": context.task_id,
                    "phase": failure_details["phase"],
                    "phase_display": failure_details["phase_display"],
                    "main_reason": failure_details["main_reason"],
                    "issues": failure_details["issues"],
                    "suggestions": failure_details["suggestions"],
                    "status": "failed",
                })
                
                await self._persist_loop_and_sediment_skills(
                    context,
                    "failed",
                    event_callback,
                )
                if event_callback:
                    event_callback(
                        "CEO Agent",
                        "workflow.run.finished",
                        "工作流失败",
                        {
                            "phase": "failed",
                            "status": "failed",
                            "failure_details": failure_details,
                        },
                    )
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
                    draft = self._apply_patent_manual_normalization(
                        draft,
                        context_title=context.title,
                    )
                    context.patent_draft = draft
                    claims_data = draft.get("claims", {})
                    description_data = draft.get("description", {})
                    abstract_text = draft.get("abstract", "")

                    docx_tool = PatentDocxGeneratorTool()
                    docx_result = await docx_tool.execute(
                        title=draft.get("title") or draft.get("patent_title") or context.title,
                        claims=claims_data,
                        description=description_data,
                        abstract=abstract_text,
                        task_id=context.task_id,
                        tech_description=self._build_confirmed_writer_context(context, limit=12000),
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
            await checkpoint("workflow_completed")
            await self._persist_loop_and_sediment_skills(
                context,
                "completed",
                event_callback,
            )
            context.brainstorming_output = {"summary": "专利申请流程已完成。需求分析→检索→撰写→审查全部通过，已生成最终文档。"}
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "workflow.run.finished",
                    "工作流完成",
                    {
                        "phase": "completed",
                        "status": "completed",
                        "final_document_path": context.metadata.get("final_document_path"),
                    },
                )
            self._logger.info("Workflow completed", task_id=context.task_id)
            return context

        except asyncio.CancelledError:
            context.current_phase = WorkflowState.CANCELLED
            raise
        except Exception as e:
            context.current_phase = WorkflowState.FAILED
            self._logger.error("Workflow failed", task_id=context.task_id, error=str(e), exc_info=True)
            await self._persist_loop_and_sediment_skills(
                context,
                "failed",
                event_callback,
            )
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
                duration_seconds=(datetime.now() - start_time).total_seconds(),
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

    def _latest_phase_output(
        self,
        context: WorkflowContext,
        phase: WorkflowPhase,
        context_field: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return latest successful phase output from history, then the context snapshot field."""
        expected = getattr(phase, "value", phase)
        for result in reversed(context.phase_history or []):
            result_phase = getattr(result.phase, "value", result.phase)
            if result_phase != expected or not result.success:
                continue
            output = self._unwrap_phase_payload(result.output)
            if isinstance(output, dict) and output:
                return output
        if context_field:
            snapshot = self._unwrap_phase_payload(getattr(context, context_field, {}))
            if isinstance(snapshot, dict) and snapshot:
                return snapshot
        return {}

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

        # 阶段契约前缀：工具提供客观信号/外部产物，阶段结论必须由对应 Hermes Agent LLM 判断。
        TOOL_FORCE_PREFIX = {
            WorkflowState.REQUIREMENT_ANALYSIS: """【需求分析阶段输出契约】
你必须先加载并遵守本 profile 的需求分析 skills，最终结论由你作为需求分析 Agent 的 LLM 判断。
可调用 transcript_sanitizer、ipc_classifier、tech_feature_extractor、scenario_miner 获取客观信号；工具结果只能作为线索，不能替代技术领域、创新点、保护主题、专利类型和信息缺口判断。
如果工具信号不足，必须在输出中如实标注 `tool_signal_insufficient`，不得用本地规则或工具空结果代替 Agent 结论。
必须基于【已确认/共享公共信息】继续完善，不得忽略启动前确认的专利名称、保护主题、专利类型、公共事实和用户补充。
如果【已确认/共享公共信息】中已有检索分析结果或本轮反馈来自检索阶段，你必须复核检索证据是否已经解决需求分析指出的缺口，并输出 `retrieval_feedback_review`：
- `all_requirement_gaps_closed`: true/false
- `remaining_requirement_gaps`: 仍未补齐的需求/证据缺口数组
- `search_feedback_for_retrieval`: 需要检索 Agent 下一轮继续解决的问题数组
- `ready_for_writing`: true/false；只有存在会导致专利文本无法完整撰写的真实技术缺口、用户专属事实缺口或需求矛盾时才设为 false。
- `carried_retrieval_risks`: 已完成多轮真实检索但仍只能作为风险带入撰写/审查的证据限制数组。
如果仍有缺口，你必须把每个缺口归属到 requirement_analysis 或 retrieval_analysis：需求/方案细节缺口由你基于上一轮内容继续补齐；证据/现有技术/真伪核验缺口写入 `search_feedback_for_retrieval` 交给检索 Agent。
用户未提供真实商业产品参数、硬件型号、尺寸、身高档位、角度档位、传感器型号、算法唯一选型时，不得默认阻止撰写；如果这些信息不是发明主题成立的必要事实，必须基于已确认方案、真实检索证据、物理规律和本领域常识写成“可配置/可选/非限定实施例”，并把限制放入 `carried_retrieval_risks` 或 `implementation_assumptions`。
只有缺口无法通过可配置范围、可选结构、非限定示例或本领域常识合理表达，且会导致权利要求骨架无法成立时，才允许把 `ready_for_writing` 设为 false。
不得仅因为“未找到单一最接近现有技术”“某个检索源不可用/无结果”“还可补充产品页面、白皮书、标准或厂商公开资料”就阻止撰写；当检索 Agent 已记录真实检索式、数据源、命中/失败/无结果和可核验对比证据时，这些事项应进入 `carried_retrieval_risks` 并交由撰写和质量审查处理。
只有补证项会改变发明主题、权利要求骨架、必要技术特征或公开状态时，才能把 `ready_for_writing` 设为 false。
不得因为检索暂时失败就要求用户补充，除非缺口是用户专属事实（例如内部产品参数、尚未公开资料、明确业务选择）。
最终 JSON 必须剔除逐字稿时间戳、说话人、寒暄和会议口语。
---

""",
            WorkflowState.RETRIEVAL_ANALYSIS: """【检索分析阶段输出契约】
你必须先加载并遵守本 profile 的检索 skills，最终检索策略、相似性、专利性和风险结论由你作为检索分析 Agent 的 LLM 判断。
patent_search、similarity_analyzer、patentability_scorer、risk_analyzer、web_access_* 都是 Hermes 工具，只提供真实检索证据、客观信号或网页取证能力；工具不能替你下结论，也不能为了满足固定顺序而空跑。
应根据需求分析提出的缺口选择必要工具：需要专利证据时调用 patent_search；已有对比文件时再调用 similarity_analyzer / patentability_scorer；需要风险线索时调用 risk_analyzer；需要非专利公开或动态页面证据时调用 web_access_*。
必须基于【已确认/共享公共信息】、需求分析结果和需求分析提出的 `information_gaps` / `search_feedback_for_retrieval` 继续检索；你的职责是为需求分析缺口补充可核验证据和可写入专利的解决方案。
如果证据不足，必须先分析为什么无结果或证据不足，再更换检索条件继续搜索；最终输出 evidence_gaps 和下一轮检索策略，不得编造检索结果。
每轮检索必须继承上一轮可用证据，新增或替换无效检索式，并说明“本轮新增证据/本轮仍未解决证据缺口/下一轮检索建议”。
检索完成后，结果必须交回需求分析 Agent 复核缺口是否关闭；你不能直接判断进入撰写。
---

""",
            WorkflowState.PATENT_WRITING: """【专利撰写阶段输出契约】
你必须先加载并遵守本 profile 的撰写、权利要求、附图和规范 skills；正式专利正文由你作为专利撰写 Agent 的 LLM 分段生成。
claim_drafter、description_writer、terminology_normalizer、support_checker 只提供结构、约束和客观信号，不能替代正式权利要求、说明书和摘要。
撰写前必须确认【已确认/共享公共信息】、需求分析和检索分析已经足够支持撰写；若不足，输出明确缺口并标注 responsible_phase，不得硬写。
对真实项目参数缺失但不影响发明成立的内容，应写成可配置范围、可选部件或非限定实施例：例如身高/角度/场景映射表、执行机构、传感器、尺寸、阈值、算法策略均可列为“可以包括/可选为/在一实施例中”，不得因为没有用户私有参数就拒绝撰写。
如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须由你调用 patent_drawing_generator 为每一张附图分别生成真实附图，且绘图输入必须来自当前专利内容。
注意：当前阶段只生成审查前的专利草稿和附图，不得调用 patent_docx_generator；最终 DOCX 必须在质量审查合格后由工作流统一生成。
---

""",
            WorkflowState.QUALITY_REVIEW: """【质量审查阶段输出契约】
你必须先加载并遵守本 profile 的质量审查 skills；最终评分、是否通过、是否需要补正和修复路径必须由你作为质量审查 Agent 的 LLM 判断。
可调用 compliance_checker、claim_quality_analyzer、support_verifier、oa_predictor 获取客观信号和审查线索；工具结果不能替代内容质量、创造性、充分公开、权利要求清楚性和附图一致性的专业判断。
必须同时审查文本、权利要求、说明书、附图是否缺失/重复、图号和附图文件可访问性。发现问题时输出可由 CEO 调度的缺陷清单。
注意：当前阶段是最终 DOCX 生成前的质量门，`docx_path` 为空不是缺陷；只有已提供最终 DOCX 路径时才审查 DOCX 插图位置。
所有 high/critical 问题必须包含 `responsible_phase`，取值只能是：requirement_analysis、retrieval_analysis、patent_writing、user_input、system_failure。
如果 recommendation 为 revise/reject 或存在 high/critical 问题，顶层必须输出 `root_cause`，取值只能是：content_incomplete、requirement_unclear、evidence_missing、external_info_missing、system_failure。
CEO 只会按这些字段路由，不会替你判断专业结论；因此必须把修复建议写成对应 Agent 可执行的反馈。
---

""",
        }

        # content_only 模式 — 用于质量门前的专利内容生成，不生成 .docx
        CONTENT_ONLY_TOOL_FORCE_PREFIX = {
            WorkflowState.PATENT_WRITING: """【专利撰写阶段输出契约】
你必须先加载并遵守本 profile 的撰写、权利要求、附图和规范 skills；正式专利正文由你作为专利撰写 Agent 的 LLM 分段生成。
claim_drafter、description_writer、terminology_normalizer、support_checker 只提供结构、约束和客观信号，不能替代正式权利要求、说明书和摘要。
撰写前必须确认【已确认/共享公共信息】、需求分析和检索分析已经足够支持撰写；若不足，输出明确缺口并标注 responsible_phase，不得硬写。
如果发明涉及结构、装置、系统、流程、空间关系或说明书包含附图说明，必须由你调用 patent_drawing_generator 为每一张附图分别生成真实附图，且绘图输入必须来自当前专利内容。
注意：工具不能替代你的专利撰写判断；不得调用 patent_docx_generator。
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
            retrieval_output = self._latest_phase_output(
                context, WorkflowPhase.RETRIEVAL, "retrieval_report"
            )
            retrieval_section = (
                "\n\n【最新检索分析结果，必须复核其是否关闭需求缺口】\n"
                + json.dumps(retrieval_output, ensure_ascii=False)[:6000]
                if retrieval_output
                else ""
            )
            return (
                f"{tool_prefix}对以下技术方案进行结构化需求分析，提取创新点和技术特征：\n\n"
                f"{base}{retrieval_section}{country_hint_map[phase]}"
            )

        elif phase == WorkflowState.RETRIEVAL_ANALYSIS:
            requirement_output = self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            )
            req = json.dumps(requirement_output, ensure_ascii=False)[:1000]
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
            requirement_output = self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            )
            retrieval_output = self._latest_phase_output(
                context, WorkflowPhase.RETRIEVAL, "retrieval_report"
            )
            req = json.dumps(requirement_output, ensure_ascii=False)[:500]
            ret = self._build_retrieval_summary_for_writer(retrieval_output, limit=8000)
            return f"{tool_prefix}基于需求分析和检索结果撰写专利申请文件：\n\n需求：{req}\n\n检索：{ret}{country_hint_map[phase]}"

        elif phase == WorkflowState.QUALITY_REVIEW:
            draft = self._build_quality_review_draft_summary(context.patent_draft)
            return f"{tool_prefix}对以下专利申请文件进行质量审查：\n\n{draft}{country_hint_map[phase]}"

        return base

    def _build_phase_continuation_prompt(
        self,
        context: WorkflowContext,
        phase: WorkflowState,
        base_prompt: str,
    ) -> str:
        """Wrap a remediation phase prompt so each round improves the last result.

        A remediation round must preserve valid parts from the previous round and
        only amend the issues that CEO/reviewer/gates identified. The Agent still
        returns a complete updated JSON so downstream rendering remains simple.
        """
        context_field = _PHASE_CONTEXT_FIELDS.get(phase)
        previous_output = getattr(context, context_field, {}) if context_field else {}
        suggestions = [
            str(item).strip()
            for item in (context.latest_revision_suggestions or [])
            if str(item).strip()
        ]
        has_previous = isinstance(previous_output, dict) and bool(previous_output)
        if not has_previous and not suggestions:
            return base_prompt

        previous_text = (
            json.dumps(previous_output, ensure_ascii=False, indent=2)[:12000]
            if has_previous
            else "无"
        )
        suggestions_text = "\n".join(
            f"{index}. {item}" for index, item in enumerate(suggestions[:20], start=1)
        ) or "无"

        return f"""{base_prompt}

---

【本轮是迭代补充/修正，不是重新开始】
你必须基于上一轮本阶段结果继续优化：
- 保留上一轮已经正确、已被后续阶段使用或已通过检查的内容；
- 只针对本轮反馈指出的问题补充、修正或替换；
- 如果需求分析更新导致检索依据变化，检索阶段应复用上一轮可用证据并补充新的检索证据，不得删除仍然有效的对比文件；
- 如果撰写阶段修正，必须保留未被反馈指出有问题的权利要求、说明书章节、摘要和附图，只修改需要修复的部分；
- 最终仍输出完整的本阶段 JSON，而不是只输出差异。

【上一轮本阶段结果】
{previous_text}

【本轮必须解决的反馈/缺口】
{suggestions_text}
"""

    def _build_quality_review_draft_summary(self, draft: Dict[str, Any]) -> str:
        if not isinstance(draft, dict):
            return str(draft)[:4000]

        claims = draft.get("claims") or {}
        description = draft.get("description") or {}
        summary = {
            "title": draft.get("title") or draft.get("patent_title") or "",
            "claims": {
                "independent_claim": str(claims.get("independent_claim") or "")[:1500],
                # Quality review must see every claim. Truncating to the first
                # few dependent claims can hide a second independent system/device
                # claim and create false remediation loops.
                "dependent_claims": [str(claim)[:1200] for claim in claims.get("dependent_claims", [])[:30]],
            },
            "description": {
                "technical_field": str(description.get("technical_field") or "")[:800],
                "background_art": str(description.get("background_art") or "")[:3000],
                "summary_of_invention": str(description.get("summary_of_invention") or "")[:3000],
                "drawings_description": str(description.get("drawings_description") or "")[:3000],
                # Reviewer must inspect the full S1-S4 implementation and figure
                # correspondence. Old short truncation made complete sections look
                # cut off and caused false "content_incomplete" loops.
                "detailed_description": str(description.get("detailed_description") or "")[:12000],
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
                "当前质量审查发生在最终 DOCX 生成前，docx_path 为空不是缺陷；通过后工作流才生成最终 DOCX。",
            ],
            "abstract": str(draft.get("abstract") or "")[:800],
            "docx_path": draft.get("docx_path") or "",
        }
        return json.dumps(summary, ensure_ascii=False)

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
        if not isinstance(review_report, dict) or not review_report:
            return True
        recommendation = str(
            review_report.get("recommendation")
            or (
                review_report.get("review_summary", {}).get("recommendation")
                if isinstance(review_report.get("review_summary"), dict)
                else ""
            )
            or ""
        ).strip().lower()
        if recommendation not in {"approve", "pass", "accept", "revise", "reject"}:
            return True
        if self._check_review_needs_revision(review_report):
            return True
        normalized_score = self._extract_normalized_review_score(review_report)
        if normalized_score is None:
            return True
        return normalized_score < QUALITY_REMEDIATION_THRESHOLD

    def _classify_remediation_path(self, review_report: Dict[str, Any], context: WorkflowContext) -> str:
        """按根因把补救动作分流为写/分析/检索/等用户/终止。"""
        if self._iteration_making_no_progress(context):
            return "TERMINAL_FAILURE"

        if not isinstance(review_report, dict):
            return "TERMINAL_FAILURE"

        root_cause = str(review_report.get("root_cause") or "").strip().lower()
        root_mapping = {
            "content_incomplete": "WRITE_MORE",
            "requirement_unclear": "ANALYZE_MORE",
            "evidence_missing": "SEARCH_MORE",
            "external_info_missing": self._route_missing_information(review_report),
            "system_failure": "TERMINAL_FAILURE",
        }
        root_route = root_mapping.get(root_cause)

        route_mapping = {
            "patent_writing": "WRITE_MORE",
            "writing": "WRITE_MORE",
            "requirement_analysis": "ANALYZE_MORE",
            "requirements": "ANALYZE_MORE",
            "retrieval_analysis": "SEARCH_MORE",
            "retrieval": "SEARCH_MORE",
            "user_input": "NEEDS_USER_INPUT",
            "system_failure": "TERMINAL_FAILURE",
        }
        routed_phases: set[str] = set()
        for issue in self._extract_review_issue_records(review_report):
            responsible_phase = str(
                issue.get("responsible_phase")
                or issue.get("target_phase")
                or issue.get("route_to")
                or ""
            ).strip().lower()
            if responsible_phase in route_mapping:
                routed_phases.add(responsible_phase)

        # A review can contain both drafting defects and evidence defects. Evidence
        # defects must be resolved before the writer is asked to revise again,
        # otherwise the writer keeps rewriting from the same incomplete source set.
        #
        # A low/medium "system_failure" note is often a non-blocking process
        # reminder such as "final DOCX has not been generated yet" during the
        # pre-DOCX quality gate. That must not terminate the agent loop.
        has_blocking_system_failure = any(
            str(issue.get("responsible_phase") or issue.get("target_phase") or issue.get("route_to") or "")
            .strip()
            .lower()
            == "system_failure"
            and str(issue.get("severity") or issue.get("likelihood") or "").strip().lower()
            in {"high", "critical"}
            for issue in self._extract_review_issue_records(review_report)
            if isinstance(issue, dict)
        )
        if has_blocking_system_failure:
            return "TERMINAL_FAILURE"

        # The reviewer-level root cause is the primary routing signal. Individual
        # risk records can name retrieval_analysis for later evidence hardening,
        # but if the reviewer's top-level cause is content_incomplete the next
        # action must be a writer revision based on the already confirmed facts.
        if root_route and root_route != "TERMINAL_FAILURE":
            return root_route

        if "retrieval_analysis" in routed_phases or "retrieval" in routed_phases:
            return "SEARCH_MORE"
        if "requirement_analysis" in routed_phases or "requirements" in routed_phases:
            return "ANALYZE_MORE"
        if "patent_writing" in routed_phases or "writing" in routed_phases:
            return "WRITE_MORE"
        if "user_input" in routed_phases:
            return "NEEDS_USER_INPUT"

        if root_route:
            return root_route

        missing_information = review_report.get("missing_information", [])
        if isinstance(missing_information, list) and any(str(item).strip() for item in missing_information):
            return self._route_missing_information(review_report)

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

        if self._needs_quality_remediation(review_report):
            return "WRITE_MORE"
        return "TERMINAL_FAILURE"

    def _route_missing_information(self, review_report: Dict[str, Any]) -> str:
        """Route missing information back to the Agent most likely to resolve it first.

        Missing information is not automatically a user-blocking state. Most
        quality findings should go back through requirement analysis or
        retrieval so Agents can refine the shared facts, change search
        strategies, and only ask the user after the remediation loop is unable
        to make progress.
        """
        if not isinstance(review_report, dict):
            return "ANALYZE_MORE"

        missing_information = review_report.get("missing_information", [])
        if not isinstance(missing_information, list):
            missing_information = [missing_information]
        text = "\n".join(str(item) for item in missing_information if str(item).strip()).lower()

        search_markers = (
            "检索",
            "证据",
            "公开",
            "网页",
            "专利",
            "prior art",
            "patent",
            "google patents",
            "uspto",
            "对比文件",
            "真伪",
            "核验",
            "来源",
        )
        if any(marker.lower() in text for marker in search_markers):
            return "SEARCH_MORE"

        return "ANALYZE_MORE"

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
                "provide_info"
                if classification in {"AUTO_REMEDIATION_LIMIT", "NEEDS_USER_INPUT"}
                else "continue_auto_fix"
            ),
            "resume_phase": self._resolve_remediation_resume_phase(classification).value,
        }

    def _prewriting_requires_user_input(self, blockers: List[Dict[str, str]]) -> bool:
        """True when the writer gate found invention facts the Agents may need from user.

        This is a classification signal, not an immediate stop condition. The CEO
        still gets remediation rounds first so the responsible Agent can reuse the
        prior result, apply feedback, search again, or infer what is reasonably
        inferable. Only after the retry budget is exhausted should the workflow
        pause for user discussion.
        """
        user_fact_markers = (
            "必须由用户",
            "需要用户提供",
            "请用户提供",
            "用户提供",
            "用户补充",
            "用户确认",
            "产品名",
            "展厅名",
            "供应商",
            "公开链接",
            "genuinely_missing",
            "external_info_missing",
        )
        agent_resolvable_markers = (
            "检索",
            "现有技术",
            "对比文件",
            "证据",
            "可核验",
            "Google Patents",
            "USPTO",
            "专业/官方",
            "交叉核验",
            "技术问题",
            "技术方案",
            "保护主题",
            "创新点",
            "权利要求骨架",
            "实施方式",
            "映射关系",
            "补偿",
            "裁切",
            "算法",
        )
        for blocker in blockers:
            if blocker.get("phase") == WorkflowState.RETRIEVAL_ANALYSIS.value:
                continue
            message = str(blocker.get("message") or "")
            if any(marker in message for marker in agent_resolvable_markers):
                continue
            if any(marker in message for marker in user_fact_markers):
                return True
        return False

    def _iter_phase_text_values(self, value: Any) -> List[str]:
        texts: List[str] = []
        if isinstance(value, str):
            if value.strip():
                texts.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                texts.extend(self._iter_phase_text_values(nested))
        elif isinstance(value, list):
            for item in value:
                texts.extend(self._iter_phase_text_values(item))
        return texts

    def _has_phase_signal(self, value: Any, *needles: str) -> bool:
        combined = "\n".join(self._iter_phase_text_values(value)).lower()
        return any(needle.lower() in combined for needle in needles)

    def _as_nonempty_list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return [item for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _is_nonblocking_prewriting_gap(
        self, gap_text: Any, retrieval_report: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Return True for limitations that should be carried as risk, not block writing.

        A single unavailable retrieval source is not a hard failure when other
        verifiable sources exist. Likewise, implementation values that can be
        expressed as ranges or alternatives should be handled by the writer and
        reviewer instead of trapping the workflow before DOCX generation.
        """
        if isinstance(gap_text, (dict, list)):
            text = "\n".join(self._iter_phase_text_values(gap_text))
        else:
            text = str(gap_text or "")
        if not text.strip():
            return True
        has_evidence = (
            isinstance(retrieval_report, dict)
            and self._has_real_retrieval_evidence(retrieval_report)
        )
        has_negative_retrieval_audit = (
            isinstance(retrieval_report, dict)
            and self._has_auditable_negative_retrieval(retrieval_report)
        )
        unavailable_source_markers = (
            "未配置",
            "未启用",
            "不可用",
            "无法访问",
            "HTTP 503",
            "解析失败",
            "未取得直接检索结果",
            "数据库覆盖",
            "覆盖不足",
            "未完成系统性直接检索",
            "尚未完成系统性直接检索",
            "未完成系统性检索",
            "系统性直接检索",
            "系统性结果",
            "稳定可核验结果",
            "直接检索",
            "宽检索",
            "英文专利宽检索",
            "继续英文专利检索",
            "商业专利库",
            "数据源",
            "不应要求用户补充",
            "最接近对比文件",
            "最接近专利文件",
            "直接披露",
            "直接公开",
            "中国专利数据库",
            "中文专利源",
            "CNIPA",
            "可核验中文",
            "未获得直接",
            "未取得任何可写入",
            "similar_patents",
            "可核验专利文献",
            "可写入",
            "公开号",
            "申请人",
            "公开日",
            "核心公开内容",
            "中文专利证据",
            "专利证据",
            "专利文献",
            "最接近专利文献",
            "行业痛点",
            "背景公开证据",
            "产品白皮书",
            "白皮书",
            "真实产品页面",
            "产品页面",
            "厂商文档",
            "厂商资料",
            "厂商公开资料",
            "行业标准",
            "标准规范",
            "商业沉浸式",
            "单一最接近文献",
            "最接近现有技术确认",
            "继续检索英文专利源",
            "继续检索中文专利源",
            "形成可审计的否定式检索结论",
        )
        if (has_evidence or has_negative_retrieval_audit) and any(
            marker in text for marker in unavailable_source_markers
        ):
            return True

        implementation_detail_markers = (
            "具体数值",
            "可公开范围",
            "尚未量化",
            "参数仍需",
            "真实商业产品",
            "真实产品",
            "真实项目",
            "真实参数",
            "工程参数",
            "研发内部",
            "范围化",
            "可选化",
            "可配置",
            "非限定",
            "实施例示例化",
            "真实产品采用",
            "公开产品采用",
            "公开功能",
            "公开时间",
            "身高区间",
            "身高档位",
            "角度档位",
            "角度阈值",
            "角度区间",
            "场景模式",
            "对应关系",
            "映射关系",
            "映射表",
            "显示模板参数",
            "执行机构",
            "执行机构型号",
            "传感器型号",
            "显示单元尺寸",
            "屏幕尺寸",
            "角度范围",
            "反馈精度",
            "具体算法",
            "唯一算法",
            "算法选型",
            "画面重构算法",
            "固定实现",
            "拟采用参数",
            "内部产品参数",
            "硬件来源",
        )
        if any(marker in text for marker in implementation_detail_markers):
            return True
        return False

    def _has_auditable_negative_retrieval(self, report: Dict[str, Any]) -> bool:
        """True when retrieval made real attempts and recorded why direct evidence is absent.

        This does not treat missing patent evidence as success. It only lets the
        writer proceed with explicit carried risks after the retrieval Agent has
        documented sources, queries, failures/no-hits, and non-patent or web
        evidence. The writer/reviewer must still cite the limitation honestly.
        """
        if not isinstance(report, dict):
            return False
        if not self._has_real_retrieval_evidence(report):
            return False

        sources = self._extract_retrieval_sources(report)
        evidence_sources = self._as_nonempty_list(report.get("evidence_sources"))
        web_evidence = self._as_nonempty_list(report.get("web_evidence"))
        non_patent = self._as_nonempty_list(report.get("non_patent_prior_art"))
        tool_results = self._as_nonempty_list(report.get("tool_results"))
        if len(sources) + len(evidence_sources) + len(web_evidence) + len(non_patent) < 3:
            return False

        audit_text = "\n".join(
            self._iter_phase_text_values(
                {
                    "retrieval_strategy": report.get("retrieval_strategy"),
                    "retrieval_keywords": report.get("retrieval_keywords"),
                    "retrieval_databases": report.get("retrieval_databases"),
                    "unavailable_sources": report.get("unavailable_sources"),
                    "empty_sources": report.get("empty_sources"),
                    "skipped_sources": report.get("skipped_sources"),
                    "evidence_gaps": report.get("evidence_gaps"),
                    "evidence_sources": report.get("evidence_sources"),
                }
            )
        )
        attempted_patent_source = any(
            marker in audit_text
            for marker in (
                "Google Patents",
                "google_patents",
                "USPTO",
                "CNIPA",
                "中国专利",
                "专利源",
                "专利库",
                "patent_search",
            )
        )
        recorded_no_hit_or_failure = any(
            marker in audit_text
            for marker in (
                "HTTP 503",
                "解析失败",
                "不可用",
                "无法访问",
                "无结果",
                "未取得",
                "未获得",
                "未命中",
                "未见直接",
                "否定式",
                "筛选记录",
            )
        )
        enough_attempts = len(tool_results) >= 3 or len(evidence_sources) >= 3
        return attempted_patent_source and recorded_no_hit_or_failure and enough_attempts

    def _filter_hard_prewriting_gaps(
        self,
        gaps: List[Any],
        retrieval_report: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        return [
            "\n".join(self._iter_phase_text_values(item))
            if isinstance(item, (dict, list))
            else str(item)
            for item in gaps
            if not self._is_nonblocking_prewriting_gap(item, retrieval_report)
        ]

    def _workflow_confirms_public_status(self, context: WorkflowContext) -> bool:
        """Return whether startup discussion already captured the invention public status."""
        confirmed = context.metadata.get("confirmed_preflight")
        if isinstance(confirmed, dict) and str(confirmed.get("public_status") or "").strip():
            return True
        shared = context.metadata.get("shared_agent_context")
        if isinstance(shared, dict):
            preflight = shared.get("confirmed_preflight")
            if isinstance(preflight, dict) and str(preflight.get("public_status") or "").strip():
                return True

        text_parts = [context.original_description]
        text_parts.extend(str(item.get("content") or "") for item in context.message_history)
        combined = "\n".join(part for part in text_parts if part).strip()
        public_status_markers = (
            "尚未公开",
            "未公开",
            "未对外公开",
            "已公开",
            "公开状态",
            "是否公开",
            "申请日前",
        )
        return any(marker in combined for marker in public_status_markers)

    def _gap_closed_by_confirmed_context(self, gap_text: Any, context: WorkflowContext) -> bool:
        text = "\n".join(self._iter_phase_text_values(gap_text)) if isinstance(gap_text, (dict, list)) else str(gap_text or "")
        if not text.strip():
            return True
        confirmed_text = self._confirmed_context_text(context)
        public_status_gap_markers = (
            "产品公开时间",
            "首次公开",
            "对外展示",
            "销售情况",
            "公开状态",
            "申请日前是否存在公开",
        )
        if any(marker in text for marker in public_status_gap_markers):
            return self._workflow_confirms_public_status(context)
        if any(marker in text for marker in ("角度阈值", "角度区间", "显示模板参数")):
            return any(
                marker in confirmed_text
                for marker in ("姿态-显示映射表", "映射表", "不写死", "显示模板参数")
            )
        if any(
            marker in text
            for marker in (
                "补充画面",
                "过渡画面",
                "裁切画面",
                "重构画面",
                "具体算法",
                "唯一算法",
            )
        ):
            return any(
                marker in confirmed_text
                for marker in (
                    "透视变换",
                    "纹理采样",
                    "时序插值",
                    "内容补全",
                    "遮挡掩膜",
                    "边缘羽化",
                    "透明度渐变",
                    "过渡帧",
                    "不限定唯一算法",
                    "可选算法族",
                )
            )
        if any(marker in text for marker in ("姿态检测", "硬件来源", "屏幕姿态检测")):
            return any(
                marker in confirmed_text
                for marker in (
                    "角度传感器",
                    "执行机构反馈",
                    "屏幕控制器状态",
                    "视觉/深度定位",
                    "深度定位",
                )
            )
        return False

    def _confirmed_context_text(self, context: WorkflowContext) -> str:
        """Return all user-confirmed/shared facts visible to workflow gates."""
        parts: List[str] = []
        parts.append(str(context.original_description or ""))
        parts.append(context.get_shared_agent_context_text(limit=20000))
        for msg in context.message_history:
            if msg.get("role") in {"user", "assistant"}:
                parts.append(str(msg.get("content") or ""))
        supplies = context.metadata.get("user_supplemental_info")
        if isinstance(supplies, list):
            parts.extend(str(item) for item in supplies)
        remediation = context.metadata.get("quality_remediation")
        if isinstance(remediation, dict):
            parts.append(str(remediation.get("user_supplied_info") or ""))
        return "\n".join(part for part in parts if part.strip())

    def _requirement_review_allows_drafting(self, retrieval_review: Dict[str, Any]) -> bool:
        """Agent-owned signal that the file can move to drafting with risks carried forward."""
        if not isinstance(retrieval_review, dict):
            return False

        if retrieval_review.get("ready_for_writing") is False:
            return False

        def is_explicitly_nonblocking_gap(item: Any) -> bool:
            if isinstance(item, dict):
                if item.get("blocking_for_writing") is False:
                    return True
                gap_text = "\n".join(
                    str(item.get(key) or "")
                    for key in (
                        "impact",
                        "impact_on_writing",
                        "reason",
                        "recommendation",
                        "gap",
                    )
                )
            else:
                gap_text = str(item or "")
            nonblocking_patterns = (
                "不应阻止撰写",
                "不阻止撰写",
                "不影响当前权利要求骨架",
                "不影响当前权利要求",
                "不影响当前撰写",
                "不改变发明主题",
                "作为检索风险带入撰写",
                "作为撰写和质量审查风险",
                "带入撰写和质量审查",
            )
            return any(pattern in gap_text for pattern in nonblocking_patterns)

        remaining = self._as_nonempty_list(retrieval_review.get("remaining_requirement_gaps"))
        hard_remaining = [
            item
            for item in remaining
            if not is_explicitly_nonblocking_gap(item)
        ]
        if retrieval_review.get("ready_for_writing") is True and (
            retrieval_review.get("all_requirement_gaps_closed") is True or not hard_remaining
        ):
            return True

        text = "\n".join(self._iter_phase_text_values(retrieval_review))
        allow_markers = (
            "具备预撰写基础",
            "可进入预撰写",
            "可启动预撰写",
            "启动预撰写",
            "可启动预撰写草案",
            "可进入预撰写草案",
            "可以进入预撰写",
            "可以启动预撰写",
            "可以进入预撰写或内部草案",
            "可以进入预撰写或内部方案草案",
            "可进入撰写",
            "可以进入撰写",
            "可进入草案",
            "可启动草案",
            "可以进入草案",
            "技术方案层面已具备预撰写基础",
            "已具备预撰写基础",
            "足以支撑预撰写",
            "足以支撑撰写",
            "已足以支撑撰写",
            "足以提示撰写",
        )
        return any(marker in text for marker in allow_markers)

    def _has_real_retrieval_evidence(self, report: Dict[str, Any]) -> bool:
        candidate_fields = (
            "prior_art_references",
            "similar_patents",
            "search_results",
            "patent_results",
            "web_evidence",
            "non_patent_prior_art",
            "evidence_sources",
        )
        for field_name in candidate_fields:
            items = report.get(field_name)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        reference_id = str(
                            item.get("reference_id")
                            or item.get("patent_id")
                            or item.get("publication_number")
                            or item.get("url")
                            or item.get("title")
                            or ""
                        ).strip()
                        if reference_id:
                            return True
                    elif str(item).strip():
                        return True
            elif isinstance(items, dict) and any(str(v).strip() for v in items.values()):
                return True
        tool_results = report.get("tool_results")
        if isinstance(tool_results, list):
            for result in tool_results:
                if not isinstance(result, dict) or result.get("success") is False:
                    continue
                result_text = "\n".join(self._iter_phase_text_values(result.get("result")))
                if re.search(r"\b(CN|US|EP|WO|JP)\s?\d{4,}", result_text, re.IGNORECASE):
                    return True
                if re.search(r"https?://", result_text):
                    return True
        return False

    def _unwrap_phase_payload(self, value: Any) -> Any:
        """Extract the Agent's structured payload from the Hermes response envelope."""
        if not isinstance(value, dict):
            return value

        metadata = {
            key: value[key]
            for key in (
                "_agent_failed",
                "_agent_error",
                "_incomplete_output",
                "tool_results",
                "duration_seconds",
            )
            if key in value
        }

        structured = value.get("structured_result")
        if isinstance(structured, dict) and structured:
            merged = dict(structured)
            for key, meta_value in metadata.items():
                merged.setdefault(key, meta_value)
            return merged

        for key in ("final_response", "output", "content", "result"):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip():
                continue
            parsed = self._try_parse_json(text)
            if isinstance(parsed, dict) and parsed and "raw_output" not in parsed:
                merged = dict(parsed)
                for meta_key, meta_value in metadata.items():
                    merged.setdefault(meta_key, meta_value)
                return merged

        return value

    def _extract_retrieval_sources(self, report: Dict[str, Any]) -> List[str]:
        """Return only sources backed by actual returned evidence."""
        sources: set[str] = set()

        actual_sources = report.get("actual_sources_used")
        if isinstance(actual_sources, list):
            sources.update(str(item).strip() for item in actual_sources if str(item).strip())

        source_counts = report.get("source_result_counts")
        if isinstance(source_counts, dict):
            for source, count in source_counts.items():
                try:
                    numeric_count = int(count)
                except (TypeError, ValueError):
                    numeric_count = 0
                if numeric_count > 0 and str(source).strip():
                    sources.add(str(source).strip())

        for field_name in ("similar_patents", "prior_art_references", "search_results", "patent_results"):
            items = report.get(field_name)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                source = (
                    item.get("source")
                    or item.get("database")
                    or item.get("data_source")
                    or item.get("provider")
                )
                if source and str(source).strip():
                    sources.add(str(source).strip())

        for field_name in ("web_evidence", "non_patent_prior_art", "evidence_sources"):
            items = report.get(field_name)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("source_url") or "").strip()
                    source = str(item.get("source") or item.get("site") or "").strip()
                else:
                    url = str(item).strip()
                    source = ""
                if source:
                    sources.add(source)
                elif "patents.google.com" in url:
                    sources.add("google_patents")
                elif "uspto.gov" in url:
                    sources.add("uspto")

        return sorted(sources)

    def _uses_public_web_evidence(self, report: Dict[str, Any]) -> bool:
        for field_name in ("web_evidence", "non_patent_prior_art", "evidence_sources"):
            if self._as_nonempty_list(report.get(field_name)):
                return True
        return False

    def _has_professional_or_official_verification(self, report: Dict[str, Any]) -> bool:
        """Check public/web evidence has a professional, official, or patent-office verifier."""
        professional_domains = (
            "patents.google.com",
            "uspto.gov",
            "patentcenter.uspto.gov",
            "ieee.org",
            "acm.org",
            "springer.com",
            "sciencedirect.com",
            "elsevier.com",
            "nature.com",
            "arxiv.org",
            "iso.org",
            "iec.ch",
        )
        verification_markers = (
            "官方",
            "专利局",
            "专业",
            "标准组织",
            "论文",
            "出版",
            "patent office",
            "official",
            "standard",
            "journal",
            "conference",
            "verified",
            "cross-check",
        )
        for field_name in ("similar_patents", "prior_art_references", "search_results", "patent_results"):
            if self._as_nonempty_list(report.get(field_name)):
                return True
        for field_name in ("web_evidence", "non_patent_prior_art", "evidence_sources"):
            for item in self._as_nonempty_list(report.get(field_name)):
                if isinstance(item, dict):
                    text = json.dumps(item, ensure_ascii=False).lower()
                    url = str(item.get("url") or item.get("source_url") or "").strip()
                else:
                    text = str(item).lower()
                    url = str(item).strip()
                if any(marker.lower() in text for marker in verification_markers):
                    return True
                host = urlparse(url).netloc.lower()
                if host.startswith("www."):
                    host = host[4:]
                if any(host == domain or host.endswith("." + domain) for domain in professional_domains):
                    return True
        return False

    def _latest_user_supplemental_text(self, context: WorkflowContext) -> str:
        parts: List[str] = []
        for msg in context.message_history:
            if msg.get("role") == "user":
                parts.append(str(msg.get("content") or ""))
        supplies = context.metadata.get("user_supplemental_info")
        if isinstance(supplies, list):
            parts.extend(str(item) for item in supplies)
        remediation = context.metadata.get("quality_remediation")
        if isinstance(remediation, dict):
            parts.append(str(remediation.get("user_supplied_info") or ""))
        return "\n".join(part for part in parts if part.strip())

    def _requirement_gap_belongs_to_retrieval(self, gap_text: str) -> bool:
        """Requirement gaps that explicitly ask retrieval to verify evidence belong to retrieval."""
        text = str(gap_text or "")
        retrieval_markers = (
            "检索分析阶段",
            "检索阶段",
            "补充检索",
            "继续检索",
            "中国专利",
            "专利库",
            "Google Patents",
            "USPTO",
            "可核验证据",
            "专业/官方",
            "官方或专业",
            "交叉核验",
            "真伪",
            "证据",
            "补证",
            "核验",
            "现有技术",
            "对比文件",
            "最接近",
            "产品页面",
            "白皮书",
            "厂商",
            "标准",
            "专利号",
        )
        return any(marker in text for marker in retrieval_markers)

    def _review_gaps_are_carriable_retrieval_risks(
        self,
        gaps: List[Any],
        retrieval_report: Optional[Dict[str, Any]],
    ) -> bool:
        """Return True when review gaps are retrieval risk notes, not drafting blockers."""
        if not gaps:
            return True
        report = retrieval_report or {}
        if not (
            self._has_real_retrieval_evidence(report)
            or self._has_auditable_negative_retrieval(report)
        ):
            return False
        for item in gaps:
            text = "\n".join(self._iter_phase_text_values(item)) if isinstance(item, (dict, list)) else str(item)
            if not text.strip():
                continue
            if self._is_nonblocking_prewriting_gap(text, report):
                continue
            if self._requirement_gap_belongs_to_retrieval(text):
                continue
            return False
        return True

    def _collect_prewriting_blockers(self, context: WorkflowContext) -> List[Dict[str, str]]:
        """Return blockers that must be resolved before the writer Agent runs.

        The gate only checks workflow readiness. It does not synthesize patent
        substance; unresolved items are routed back to the responsible Hermes Agent.
        """
        blockers: List[Dict[str, str]] = []
        req = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        if not isinstance(req, dict) or not req:
            return [{
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "critical",
                "message": "需求分析结果缺失，不能进入专利撰写。",
            }]
        if req.get("_agent_failed") is True:
            blockers.append({
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "critical",
                "message": f"需求分析 Agent 执行失败：{str(req.get('_agent_error') or '')[:220]}",
            })

        required_requirement_fields = [
            ("tech_field", "技术领域"),
            ("core_principle", "核心原理"),
            ("technical_problem", "技术问题"),
            ("beneficial_effects", "有益效果"),
            ("key_innovative_features", "关键创新特征"),
            ("application_scenarios", "应用场景"),
            ("patent_type_recommendation", "专利类型建议"),
            ("claim_skeleton", "权利要求骨架"),
        ]
        for field_name, label in required_requirement_fields:
            value = req.get(field_name)
            if isinstance(value, dict):
                has_value = any(str(v).strip() for v in value.values())
            elif isinstance(value, list):
                has_value = bool(self._as_nonempty_list(value))
            else:
                has_value = bool(str(value or "").strip())
            if not has_value:
                blockers.append({
                    "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                    "severity": "high",
                    "message": f"需求分析缺少{label}，撰写前必须由需求分析 Agent 补齐。",
                })

        claim_skeleton = req.get("claim_skeleton")
        if isinstance(claim_skeleton, dict):
            step_count = claim_skeleton.get("step_count")
            steps = claim_skeleton.get("steps")
            actual_step_count = len(steps) if isinstance(steps, list) else step_count
            if actual_step_count not in (3, 4):
                blockers.append({
                    "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                    "severity": "high",
                    "message": "需求分析中的独权骨架不是3步或4步，必须先修正保护方案再撰写。",
                })

        ret_preview = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        if not isinstance(ret_preview, dict) or not ret_preview:
            ret_preview = None
        retrieval_review = req.get("retrieval_feedback_review")
        review_allows_drafting = (
            self._requirement_review_allows_drafting(retrieval_review)
            if isinstance(retrieval_review, dict)
            else False
        )
        has_real_retrieval_evidence = self._has_real_retrieval_evidence(ret_preview or {})
        requirement_allows_drafting = (
            bool(req.get("can_start_drafting") is True or req.get("ready_for_writing") is True)
            or self._requirement_review_allows_drafting(req)
        )

        raw_information_gaps = [
            item
            for item in self._as_nonempty_list(req.get("information_gaps"))
            if not self._gap_closed_by_confirmed_context(item, context)
        ]
        gaps = self._filter_hard_prewriting_gaps(raw_information_gaps, ret_preview)
        filtered_gaps: List[str] = []
        retrieval_gaps: List[str] = []
        for gap in gaps:
            gap_text = str(gap)
            if self._requirement_gap_belongs_to_retrieval(gap_text):
                retrieval_gaps.append(gap_text)
                continue
            filtered_gaps.append(gap_text)
        if review_allows_drafting:
            carried = context.metadata.setdefault("prewriting_carried_risks", {})
            if filtered_gaps:
                carried["requirement_information_gaps"] = filtered_gaps
            if retrieval_gaps:
                carried["retrieval_information_gaps"] = retrieval_gaps
            filtered_gaps = []
            retrieval_gaps = []
        elif requirement_allows_drafting and (
            has_real_retrieval_evidence
            or self._has_auditable_negative_retrieval(ret_preview or {})
        ):
            carried = context.metadata.setdefault("prewriting_carried_risks", {})
            if filtered_gaps:
                carried["requirement_information_gaps"] = filtered_gaps
            if retrieval_gaps:
                carried["retrieval_information_gaps"] = retrieval_gaps
            carried["requirement_review_conclusion"] = str(
                req.get("analysis_confidence_note")
                or req.get("review_conclusion")
                or "需求分析 Agent 已确认足以支撑撰写。"
            )[:2000]
            filtered_gaps = []
            retrieval_gaps = []
        if filtered_gaps:
            blockers.append({
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "high",
                "message": "需求分析仍存在信息缺口，不能直接交给撰写 Agent：" + "；".join(str(item)[:120] for item in filtered_gaps[:5]),
            })
        if retrieval_gaps:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "需求分析指出仍需检索阶段补证/核验，不能进入撰写：" + "；".join(str(item)[:120] for item in retrieval_gaps[:5]),
            })
        if self._has_phase_signal(req, "knowledge_insufficient", "genuinely_missing"):
            blockers.append({
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "high",
                "message": "需求分析标记了未解决的信息不足信号，必须先由 CEO 调度补齐或确认。",
            })
        if (
            self._retrieval_has_requirement_review(context)
            and not isinstance(retrieval_review, dict)
            and not (
                requirement_allows_drafting
                and (
                    has_real_retrieval_evidence
                    or self._has_auditable_negative_retrieval(ret_preview or {})
                )
            )
        ):
            blockers.append({
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "high",
                "message": "需求分析已在检索后更新，但未输出 retrieval_feedback_review，必须由需求分析 Agent 明确复核检索是否关闭缺口。",
            })
        if isinstance(retrieval_review, dict):
            ready_for_writing = retrieval_review.get("ready_for_writing")
            all_gaps_closed = retrieval_review.get("all_requirement_gaps_closed")
            raw_remaining = [
                item
                for item in self._as_nonempty_list(
                    retrieval_review.get("remaining_requirement_gaps")
                )
                if not self._gap_closed_by_confirmed_context(item, context)
            ]
            raw_search_feedback = self._as_nonempty_list(
                retrieval_review.get("search_feedback_for_retrieval")
            )
            remaining = self._filter_hard_prewriting_gaps(raw_remaining, ret_preview)
            search_feedback = self._filter_hard_prewriting_gaps(raw_search_feedback, ret_preview)
            carriable_retrieval_risks = (
                self._review_gaps_are_carriable_retrieval_risks(raw_remaining, ret_preview)
                and self._review_gaps_are_carriable_retrieval_risks(
                    raw_search_feedback,
                    ret_preview,
                )
            )
            if review_allows_drafting:
                context.metadata["prewriting_carried_risks"] = {
                    "remaining_requirement_gaps": remaining,
                    "search_feedback_for_retrieval": search_feedback,
                    "review_conclusion": retrieval_review.get("review_conclusion"),
                    "policy": (
                        "需求分析 Agent 已明确 ready_for_writing=true，"
                        "剩余检索项仅作为撰写和质量审查风险继续流转，"
                        "不再触发检索无限循环。"
                    ),
                }
                remaining = []
                search_feedback = []
                ready_for_writing = True
                all_gaps_closed = True
            elif carriable_retrieval_risks:
                carried = context.metadata.setdefault("prewriting_carried_risks", {})
                carried["remaining_requirement_gaps"] = raw_remaining
                carried["search_feedback_for_retrieval"] = raw_search_feedback
                carried["review_conclusion"] = retrieval_review.get("review_conclusion")
                carried["policy"] = (
                    "需求分析复核中的剩余项均为检索证据增强或来源限制；"
                    "已有真实检索证据/失败审计，作为撰写和质量审查风险继续流转。"
                )
                remaining = []
                search_feedback = []
                ready_for_writing = True
                all_gaps_closed = True
            hard_review_blocked = bool(remaining or search_feedback)
            soft_review_flag_only = (
                (review_allows_drafting or not hard_review_blocked)
                and has_real_retrieval_evidence
                and (ready_for_writing is not True or all_gaps_closed is not True)
            )
            if (
                (ready_for_writing is not True or all_gaps_closed is not True or hard_review_blocked)
                and not soft_review_flag_only
            ):
                target_phase = (
                    WorkflowState.RETRIEVAL_ANALYSIS.value
                    if search_feedback or any(self._requirement_gap_belongs_to_retrieval(str(item)) for item in remaining)
                    else WorkflowState.REQUIREMENT_ANALYSIS.value
                )
                detail = "；".join(str(item)[:120] for item in (search_feedback or remaining)[:5])
                if not detail:
                    detail = (
                        "需求分析复核未明确 ready_for_writing=true 且 "
                        "all_requirement_gaps_closed=true，不能进入撰写。"
                    )
                blockers.append({
                    "phase": target_phase,
                    "severity": "high",
                    "message": "需求分析复核认为检索/需求缺口尚未关闭：" + detail,
                })

        ret = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        if not isinstance(ret, dict) or not ret:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "critical",
                "message": "检索分析结果缺失，不能进入专利撰写。",
            })
            return blockers
        if ret.get("_agent_failed") is True:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "critical",
                "message": f"检索分析 Agent 执行失败：{str(ret.get('_agent_error') or '')[:220]}",
            })

        strategy = ret.get("retrieval_strategy")
        if isinstance(strategy, dict):
            keywords = self._as_nonempty_list(strategy.get("keywords") or ret.get("retrieval_keywords"))
            declared_databases = self._as_nonempty_list(strategy.get("databases_used") or ret.get("retrieval_databases"))
        else:
            keywords = self._as_nonempty_list(ret.get("retrieval_keywords"))
            declared_databases = self._as_nonempty_list(ret.get("retrieval_databases"))
        databases = self._extract_retrieval_sources(ret)
        if not databases and declared_databases and self._has_real_retrieval_evidence(ret):
            databases = declared_databases
        if len(keywords) < 3:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索策略缺少足够的实际检索关键词，必须补充检索。",
            })
        if not databases:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索报告未记录实际使用的数据源，必须补充检索证据。",
            })
        if not self._has_real_retrieval_evidence(ret):
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索报告没有可核验的专利或网页证据列表，不能进入撰写。",
            })
        else:
            skipped_sources = self._as_nonempty_list(ret.get("skipped_sources"))
            empty_sources = self._as_nonempty_list(ret.get("empty_sources"))
            unavailable_sources = self._as_nonempty_list(
                ret.get("unavailable_sources")
                or (strategy.get("unavailable_sources") if isinstance(strategy, dict) else [])
            )
            if skipped_sources or empty_sources or unavailable_sources:
                context.metadata.setdefault("prewriting_carried_risks", {})[
                    "retrieval_source_limitations"
                ] = {
                    "skipped_sources": skipped_sources,
                    "empty_sources": empty_sources,
                    "unavailable_sources": unavailable_sources,
                    "policy": (
                        "单个或部分检索源不可用/无结果时跳过并记录；"
                        "只要其他真实来源已有可核验证据，不作为进入撰写的硬阻断。"
                    ),
                }
        if self._uses_public_web_evidence(ret) and not self._has_professional_or_official_verification(ret):
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索报告使用了公开网页或 Google Patents 候选证据，但没有专业/官方来源交叉核验，必须继续核验真伪。",
            })
        retrieval_has_newer_requirement_review = self._retrieval_has_requirement_review(context)
        evidence_gaps = self._filter_hard_prewriting_gaps(
            self._as_nonempty_list(ret.get("evidence_gaps")),
            ret,
        )
        latest_requirement_approves_retrieval = (
            retrieval_has_newer_requirement_review
            and (review_allows_drafting or requirement_allows_drafting)
            and self._has_real_retrieval_evidence(ret)
        )
        if evidence_gaps and latest_requirement_approves_retrieval:
            context.metadata.setdefault("prewriting_carried_risks", {})[
                "retrieval_evidence_gaps"
            ] = {
                "items": evidence_gaps,
                "policy": (
                    "检索 Agent 已返回真实可核验证据，且更新后的需求分析 Agent "
                    "已确认需求缺口可进入撰写；剩余证据限制转交撰写/质检阶段处理，"
                    "不再触发检索无限循环。"
                ),
            }
            evidence_gaps = []
        if evidence_gaps and not retrieval_has_newer_requirement_review:
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索报告仍存在证据缺口：" + "；".join(str(item)[:120] for item in evidence_gaps[:5]),
            })
        has_retrieval_signal = self._has_phase_signal(
            ret,
            "data_source_unavailable",
            "insufficient_evidence",
            "no_results",
        )
        if (
            has_retrieval_signal
            and not retrieval_has_newer_requirement_review
            and (not self._has_real_retrieval_evidence(ret) or evidence_gaps)
        ):
            blockers.append({
                "phase": WorkflowState.RETRIEVAL_ANALYSIS.value,
                "severity": "high",
                "message": "检索报告标记了数据源不可用、无结果或证据不足，必须继续调度检索 Agent 扩展检索。",
            })
        if not retrieval_has_newer_requirement_review:
            blockers.append({
                "phase": WorkflowState.REQUIREMENT_ANALYSIS.value,
                "severity": "high",
                "code": "retrieval_needs_requirement_review",
                "message": "检索分析已更新，但尚未交回需求分析 Agent 复核需求缺口是否全部关闭，不能进入撰写。",
            })

        return blockers

    def _select_prewriting_remediation_phase(self, blockers: List[Dict[str, str]]) -> WorkflowState:
        if any(item.get("code") == "retrieval_needs_requirement_review" for item in blockers):
            return WorkflowState.REQUIREMENT_ANALYSIS
        phases = {item.get("phase") for item in blockers}
        if WorkflowState.RETRIEVAL_ANALYSIS.value in phases:
            return WorkflowState.RETRIEVAL_ANALYSIS
        if WorkflowState.REQUIREMENT_ANALYSIS.value in phases:
            return WorkflowState.REQUIREMENT_ANALYSIS
        return WorkflowState.RETRIEVAL_ANALYSIS

    def _prewriting_blockers_are_retrieval_only(self, blockers: List[Dict[str, str]]) -> bool:
        return bool(blockers) and all(
            item.get("phase") == WorkflowState.RETRIEVAL_ANALYSIS.value for item in blockers
        )

    def _latest_phase_history_index(self, context: WorkflowContext, phase: WorkflowPhase) -> int:
        """Return latest successful phase index in history, or -1 when absent."""
        latest = -1
        expected_phase = getattr(phase, "value", phase)
        for index, result in enumerate(context.phase_history):
            result_phase = getattr(result.phase, "value", result.phase)
            if result_phase == expected_phase and result.success:
                latest = index
        return latest

    def _retrieval_has_requirement_review(self, context: WorkflowContext) -> bool:
        """A retrieval report may feed writing only after requirement Agent reviews it.

        This enforces the domain collaboration loop:
        requirement gaps -> retrieval evidence -> requirement confirmation -> writing.
        The workflow engine does not decide whether the evidence is enough; it only
        requires that the responsible requirement Agent has produced a newer round
        after the latest retrieval round.
        """
        latest_retrieval = self._latest_phase_history_index(context, WorkflowPhase.RETRIEVAL)
        if latest_retrieval < 0:
            return False
        latest_requirement = self._latest_phase_history_index(context, WorkflowPhase.REQUIREMENT)
        return latest_requirement > latest_retrieval

    def _blockers_only_require_retrieval_review(self, blockers: List[Dict[str, str]]) -> bool:
        return bool(blockers) and all(
            item.get("code") == "retrieval_needs_requirement_review"
            for item in blockers
        )

    async def _ensure_prewriting_ready(
        self,
        context: WorkflowContext,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        checkpoint_callback: Optional[Callable[[WorkflowContext, str], None | Awaitable[None]]] = None,
        max_attempts: int = 8,
    ) -> bool:
        attempts = int(context.metadata.get("prewriting_gate_attempts", 0) or 0)
        remediation = context.metadata.get("quality_remediation")
        if (
            isinstance(remediation, dict)
            and remediation.get("classification") == "service_restarted_resume_required"
            and context.current_phase != WorkflowState.AWAITING_USER_DECISION
        ):
            context.metadata.pop("quality_remediation", None)

        while True:
            blockers = self._collect_prewriting_blockers(context)
            if not blockers:
                context.metadata.pop("prewriting_gate_blockers", None)
                remediation = context.metadata.get("quality_remediation")
                if isinstance(remediation, dict) and str(
                    remediation.get("classification") or ""
                ).startswith("prewriting_"):
                    context.metadata.pop("quality_remediation", None)
                context.metadata["prewriting_gate_passed"] = True
                if attempts and event_callback:
                    event_callback(
                        "CEO Agent",
                        "agent.content",
                        "✅ 撰写前置检查已通过：需求分析和检索问题已处理完毕",
                        {
                            "agent_name": "CEO Agent",
                            "phase": "prewriting_gate",
                            "content": "需求分析和检索分析已满足撰写前置条件。",
                        },
                    )
                return True

            context.metadata["prewriting_gate_passed"] = False
            context.metadata["prewriting_gate_blockers"] = blockers
            context.latest_revision_suggestions = [item["message"] for item in blockers]
            issue_text = "\n".join(
                f"{index}. [{item.get('phase')}] {item.get('message')}"
                for index, item in enumerate(blockers[:12], start=1)
            )
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.content",
                    "🛑 撰写前置检查未通过，先补齐需求/检索问题\n" + issue_text,
                    {
                        "agent_name": "CEO Agent",
                        "phase": "prewriting_gate",
                        "content": issue_text,
                        "blockers": blockers,
                        "attempt": attempts,
                    },
                )

            needs_requirement_review = any(
                item.get("code") == "retrieval_needs_requirement_review"
                for item in blockers
            )
            if needs_requirement_review:
                if event_callback:
                    event_callback(
                        "CEO Agent",
                        "agent.dispatch",
                        "🎯 检索结果已更新，先交回 → 需求分析 Agent 复核缺口关闭情况",
                        {
                            "from_agent": "CEO Agent",
                            "to_agent": _PHASE_DISPLAY_NAMES.get(
                                WorkflowState.REQUIREMENT_ANALYSIS,
                                "需求分析 Agent",
                            ),
                            "phase": "prewriting_gate",
                            "task_description": issue_text[:1200],
                            "attempt": attempts,
                        },
                    )
                context.latest_revision_suggestions = [issue_text]
                await self._execute_remediation_phase(
                    context,
                    WorkflowState.REQUIREMENT_ANALYSIS,
                    event_callback=event_callback,
                    phase_callback=phase_callback,
                    checkpoint_callback=checkpoint_callback,
                )
                continue

            needs_user_input = self._prewriting_requires_user_input(blockers)
            retrieval_only = self._prewriting_blockers_are_retrieval_only(blockers)
            retrieval_max_attempts = max(max_attempts, 10)
            effective_max_attempts = retrieval_max_attempts if retrieval_only else max_attempts
            should_discuss_with_user = attempts >= effective_max_attempts
            if should_discuss_with_user and not needs_user_input and not retrieval_only:
                has_requirement_blocker = any(
                    item.get("phase") == WorkflowState.REQUIREMENT_ANALYSIS.value
                    for item in blockers
                )
                if has_requirement_blocker:
                    # Requirement-stage gaps such as implementation variants,
                    # feature mappings, and interaction details should be
                    # refined by the requirement Agent before asking the user.
                    effective_max_attempts = max(effective_max_attempts, 12)
                    should_discuss_with_user = attempts >= effective_max_attempts
            if should_discuss_with_user:
                context.current_phase = WorkflowState.AWAITING_USER_DECISION
                if retrieval_only and not needs_user_input:
                    classification = "retrieval_evidence_discussion_required"
                    hold_message = (
                        "⏸️ 多轮补检后仍无法获得足够可核验证据，需要与用户讨论补充检索线索，"
                        "之后再由 CEO 继续调度检索 Agent。"
                    )
                else:
                    classification = (
                        "prewriting_user_input_required"
                        if needs_user_input
                        else "prewriting_gate_blocked"
                    )
                    hold_message = (
                        "⏸️ 撰写前置闭环已达到自动处理上限，需要与用户讨论后继续。"
                        if not needs_user_input
                        else "⏸️ 撰写前还缺少必须由用户确认的信息，已暂停自动流程。"
                    )
                context.metadata["quality_remediation"] = {
                    "classification": classification,
                    "missing_information": [item["message"] for item in blockers],
                    "attempt_count": attempts,
                    "recommended_next_action": "provide_info",
                    "resume_phase": self._select_prewriting_remediation_phase(blockers).value,
                }
                if event_callback:
                    event_callback(
                        "CEO Agent",
                        "workflow.human_input.requested",
                        hold_message,
                        {
                            "phase": "prewriting_gate",
                            "phase_node": "user_interrupt",
                            "blockers": blockers,
                            "attempt": attempts,
                            "interrupt_type": classification,
                            "resume_phase": context.metadata.get("quality_remediation", {}).get("resume_phase"),
                        },
                    )
                    event_callback(
                        "CEO Agent",
                        "agent.content",
                        hold_message + "\n" + issue_text,
                        {
                            "agent_name": "CEO Agent",
                            "phase": "prewriting_gate",
                            "content": issue_text,
                            "blockers": blockers,
                            "attempt": attempts,
                        },
                    )
                await self._publish_progress_event(
                    context,
                    WorkflowState.AWAITING_USER_DECISION,
                    "waiting",
                )
                if checkpoint_callback:
                    result = checkpoint_callback(context, "prewriting_gate_waiting")
                    if asyncio.iscoroutine(result):
                        await result
                return False

            attempts += 1
            context.metadata["prewriting_gate_attempts"] = attempts
            phase = self._select_prewriting_remediation_phase(blockers)
            dispatch_text = issue_text
            if phase == WorkflowState.RETRIEVAL_ANALYSIS:
                dispatch_text += (
                    "\n\n检索补全要求：先分析为什么无结果或证据不足；"
                    "然后更换检索条件，使用更宽/更窄、中文/英文、同义词和关键技术特征组合继续检索；"
                    "必要时补充公开网页或 Google Patents 证据，并用专业信息网站或官方来源交叉确认真伪；"
                    "禁止编造专利号、申请人、公开日或网页来源。"
                )
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.dispatch",
                    f"🎯 撰写前置检查要求先调度 → {_PHASE_DISPLAY_NAMES.get(phase, phase.value)}（第{attempts}轮）",
                    {
                        "from_agent": "CEO Agent",
                        "to_agent": _PHASE_DISPLAY_NAMES.get(phase, phase.value),
                        "phase": "prewriting_gate",
                        "task_description": dispatch_text[:1200],
                        "attempt": attempts,
                    },
                )
            context.latest_revision_suggestions = [dispatch_text]
            await self._execute_remediation_phase(
                context,
                phase,
                event_callback=event_callback,
                phase_callback=phase_callback,
                checkpoint_callback=checkpoint_callback,
            )
            if (
                phase == WorkflowState.REQUIREMENT_ANALYSIS
                and not self._blockers_only_require_retrieval_review(blockers)
            ):
                if event_callback:
                    event_callback(
                        "CEO Agent",
                        "agent.dispatch",
                        "🎯 需求分析已更新，重新调度 → 检索分析 Agent",
                        {
                            "from_agent": "CEO Agent",
                            "to_agent": _PHASE_DISPLAY_NAMES.get(
                                WorkflowState.RETRIEVAL_ANALYSIS,
                                "检索分析 Agent",
                            ),
                            "phase": "prewriting_gate",
                            "attempt": attempts,
                        },
                    )
                await self._execute_remediation_phase(
                    context,
                    WorkflowState.RETRIEVAL_ANALYSIS,
                    event_callback=event_callback,
                    phase_callback=phase_callback,
                    checkpoint_callback=checkpoint_callback,
                )

    async def _execute_remediation_phase(
        self,
        context: WorkflowContext,
        phase_state: WorkflowState,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        phase_callback: Optional[Callable[[WorkflowState, PhaseResult], None | Awaitable[None]]] = None,
        checkpoint_callback: Optional[Callable[[WorkflowContext, str], None | Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """复用现有 phase prompt/normalize 逻辑执行单个补救阶段。"""
        if phase_state not in _PHASE_TO_PROFILE or phase_state not in _PHASE_CONTEXT_FIELDS:
            raise ValueError(f"Unsupported remediation phase: {phase_state.value}")

        phase_started_at = time.perf_counter()
        service = _get_agent_factory()
        context.current_phase = phase_state
        await self._publish_progress_event(context, phase_state, "running")
        context_field = _PHASE_CONTEXT_FIELDS[phase_state]
        phase_node = self._node_for_context_field(context_field)
        phase_round = self._phase_round_index(context, phase_node)
        if event_callback:
            event_callback(
                _PHASE_DISPLAY_NAMES.get(phase_state, phase_state.value),
                "workflow.phase_round.started",
                f"{_PHASE_DISPLAY_NAMES.get(phase_state, phase_state.value)} 第{phase_round}轮补救开始",
                {
                    "phase": phase_state.value,
                    "phase_node": phase_node,
                    "round": phase_round,
                    "context_field": context_field,
                    "input_contract": self._phase_contract_summary(context_field),
                    "remediation": True,
                },
            )
        if checkpoint_callback:
            result = checkpoint_callback(context, f"{phase_state.value}_remediation_running")
            if asyncio.iscoroutine(result):
                await result

        task_desc = self._build_phase_continuation_prompt(
            context,
            phase_state,
            self._build_phase_prompt(context, phase_state),
        )
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
            if isinstance(context_data, dict):
                context_data = await self._ensure_required_patent_drawings(
                    context,
                    context_data,
                    event_callback=event_callback,
                )
                context_data = self._apply_patent_manual_normalization(
                    context_data,
                    context_title=context.title,
                )
                context_data = await self._refresh_working_draft_docx(
                    context,
                    context_data,
                    checkpoint="补救撰写",
                    event_callback=event_callback,
                )
                context_data = self._clear_stale_writer_failure_if_reviewable(context_data)
                context_data["_writer_postprocessed"] = True
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
            agent_profile_id = {
                WorkflowState.REQUIREMENT_ANALYSIS: "requirement_analyst",
                WorkflowState.RETRIEVAL_ANALYSIS: "retrieval_analyst",
                WorkflowState.QUALITY_REVIEW: "quality_reviewer",
            }.get(phase_state, phase_state.value)
            context_data = self._build_context_data_from_agent_response(
                agent_profile_id,
                agent_text,
                agent_tool_results,
                agent_result.get("structured_result"),
            )

        context_data = self._normalize_phase_output(context_field, context_data)
        contract_issues = self._validate_phase_contract(context_field, context_data)
        if contract_issues:
            context_data = self._build_phase_contract_error(
                context_field,
                context_data,
                contract_issues,
            )
        phase_duration = time.perf_counter() - phase_started_at
        if isinstance(context_data, dict):
            context_data.setdefault("_phase_duration_seconds", phase_duration)
        setattr(context, context_field, context_data)
        previous_shared_facts_version = int(context.metadata.get("shared_facts_version") or 0)
        self._update_shared_context_from_phase(context, context_field, context_data)
        if event_callback and int(context.metadata.get("shared_facts_version") or 0) != previous_shared_facts_version:
            event_callback(
                agent_display_name,
                "workflow.shared_facts.updated",
                f"{agent_display_name} 更新了公共事实",
                {
                    "phase": phase_state.value,
                    "phase_node": phase_node,
                    "round": phase_round,
                    "shared_facts_version": context.metadata.get("shared_facts_version"),
                    "shared_facts_delta": self._summarize_for_checkpoint(
                        context_data.get("shared_facts_delta") if isinstance(context_data, dict) else {},
                        limit=3000,
                    ),
                    "remediation": True,
                },
            )

        saved_path = None
        try:
            saved_path = _persist_phase_result(
                context.task_id,
                context_field,
                context_data if isinstance(context_data, dict) else {"output": str(context_data)},
            )
        except Exception:
            pass

        phase_enum = _PHASE_TO_WORKFLOW_PHASE.get(phase_state, WorkflowPhase.BRAINSTORM)
        agent_failed = isinstance(context_data, dict) and context_data.get("_agent_failed") is True
        if not agent_failed:
            self._invalidate_downstream_outputs(
                context,
                phase_state,
                reason="remediation_phase_completed",
                preserve_fields=self._preserve_downstream_fields_after_phase(
                    phase_state,
                    context_data,
                ),
            )
        phase_result = PhaseResult(
            phase=phase_enum,
            success=not agent_failed,
            duration_seconds=phase_duration,
            output=context_data if isinstance(context_data, dict) else {},
            issues=[str(context_data.get("_agent_error", ""))] if agent_failed and isinstance(context_data, dict) else [],
        )
        context.add_phase_result(phase_result)
        round_record = self._record_phase_round(
            context,
            node=phase_node,
            context_field=context_field,
            status="failed" if agent_failed else "completed",
            output=context_data,
            duration_seconds=phase_duration,
            issues=phase_result.issues,
            artifact_path=saved_path,
        )

        if event_callback:
            event_callback(
                agent_display_name,
                "agent.content",
                "📄 输出",
                {"agent_name": agent_display_name, "content": agent_text if agent_text else "", "phase": phase_state.value},
            )
            event_callback(
                agent_display_name,
                "workflow.phase_round.completed",
                f"{agent_display_name} 第{phase_round}轮补救{'失败' if agent_failed else '完成'}",
                {
                    "phase": phase_state.value,
                    "phase_node": phase_node,
                    "round": phase_round,
                    "round_record": round_record,
                    "remediation": True,
                },
            )

        await self._publish_progress_event(context, phase_state, "failed" if agent_failed else "completed")
        if phase_callback:
            result = phase_callback(phase_state, phase_result)
            if asyncio.iscoroutine(result):
                await result
        if checkpoint_callback:
            result = checkpoint_callback(
                context,
                f"{phase_state.value}_remediation_{'failed' if agent_failed else 'completed'}",
            )
            if asyncio.iscoroutine(result):
                await result
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

    def _extract_review_issue_records(self, review_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract structured review issues for CEO routing without judging quality."""
        if not isinstance(review_report, dict):
            return []

        records: List[Dict[str, Any]] = []
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
            if not isinstance(section, dict):
                continue
            for issue in section.get("issues", []):
                if isinstance(issue, dict):
                    record = dict(issue)
                    record.setdefault("section", section_key)
                    records.append(record)

        for risk in review_report.get("examination_risks", []):
            if isinstance(risk, dict):
                record = dict(risk)
                record.setdefault("section", "examination_risks")
                records.append(record)

        for suggestion in review_report.get("detailed_revision_suggestions", []):
            if isinstance(suggestion, dict):
                record = dict(suggestion)
                record.setdefault("section", suggestion.get("section") or "revision_suggestions")
                records.append(record)

        return records

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
            and self._drawing_artifact_is_accessible(drawing)
            for drawing in drawings
        )

    def _drawing_artifact_is_accessible(self, drawing: Dict[str, Any]) -> bool:
        """Return True when a drawing has a workflow-accessible artifact reference."""
        artifact_url = drawing.get("artifact_url") or drawing.get("artifactUrl")
        if artifact_url:
            return True
        file_path = drawing.get("file_path") or drawing.get("path")
        if not file_path:
            return False
        try:
            return _Path(str(file_path)).exists()
        except (OSError, ValueError):
            return False

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
            and self._drawing_artifact_is_accessible(drawing)
        }
        return [figure for figure in referenced if figure not in generated]

    def _planned_drawing_specs(self, draft: Dict[str, Any]) -> List[Dict[str, str]]:
        """Return figure specs explicitly provided by the Agent draft.

        The workflow must not invent drawing content. It only normalizes figures
        that already appear in the writer's drawing metadata or drawing-description
        section, then asks the writer Agent to generate missing artifacts.
        """
        if not isinstance(draft, dict):
            return []

        description = draft.get("description", {}) or {}
        if not isinstance(description, dict):
            description = {}
        specs_by_number: Dict[str, Dict[str, str]] = {}

        drawings = draft.get("drawings", [])
        if isinstance(drawings, list):
            for item in drawings:
                if not isinstance(item, dict):
                    continue
                figure_number = str(item.get("figure_number") or item.get("figure") or "").replace(" ", "")
                if not re.fullmatch(r"图\d+", figure_number):
                    continue
                title = str(item.get("title") or f"{figure_number}附图").strip()
                desc = str(item.get("description") or item.get("caption") or "").strip()
                specs_by_number[figure_number] = {
                    "figure_number": figure_number,
                    "title": title,
                    "description": desc,
                }

        drawing_text = str(
            description.get("drawings_description")
            or description.get("description_of_drawings")
            or ""
        )
        for match in re.finditer(r"(图\d+)[^\n。；;]*[。；;\n]?", drawing_text):
            sentence = match.group(0).strip(" \n；;。")
            figure_number = match.group(1).replace(" ", "")
            if not sentence:
                continue
            existing = specs_by_number.get(figure_number, {})
            title = existing.get("title") or sentence
            if len(title) > 30:
                title = f"{figure_number}附图"
            specs_by_number[figure_number] = {
                "figure_number": figure_number,
                "title": title,
                "description": existing.get("description") or sentence,
            }

        def _figure_sort_key(item: Dict[str, str]) -> int:
            digits = re.sub(r"\D+", "", item.get("figure_number", ""))
            return int(digits or 0)

        return sorted(specs_by_number.values(), key=_figure_sort_key)

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
        if self._draft_requires_drawings(draft) and not planned_specs:
            draft["_drawing_plan_required"] = {
                "issue": "需要附图，但专利撰写 Agent 未给出逐图附图说明和绘图内容",
                "required_action": "请专利撰写 Agent 先补齐每张附图的图号、标题、具体绘图内容，再调用生图工具。",
            }
            if event_callback:
                event_callback(
                    "CEO Agent",
                    "agent.content",
                    "🧭 需要附图但缺少逐图绘图方案，已交回专利撰写 Agent 补齐",
                    {
                        "agent_name": "CEO Agent",
                        "phase": "patent_writing",
                        "content": json.dumps(draft["_drawing_plan_required"], ensure_ascii=False),
                    },
                )
            return draft
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
            or ""
        )
        if event_callback:
            event_callback(
                "专利撰写 Agent",
                "agent.thinking",
                f"🖼️ 草稿需要补齐附图（{', '.join(missing_figures)}），正在调用生图工具...",
                {"agent_name": "专利撰写 Agent", "thought": "生成专利附图", "phase": "patent_writing", "missing_figures": missing_figures},
            )

        try:
            drawing_specs = [spec_by_number.get(number, {"figure_number": number}) for number in missing_figures]
            agent_prompt = f"""你是专利撰写 Agent。当前草稿引用了附图，但缺少可访问的附图文件。

请你基于当前专利草稿中已经写明的逐图附图说明，通过 Hermes 工具 `patent_drawing_generator` 分别生成缺失附图。
工作流只负责把缺失图号和草稿上下文交给你，不能代替你决定图中技术内容或调用生图工具。

【任务 ID】
{context.task_id}

【缺失附图规格】
{json.dumps(drawing_specs, ensure_ascii=False, indent=2)}

【附图说明上下文】
{drawing_description}

【已确认技术方案上下文】
{self._build_confirmed_writer_context(context, limit=12000)}

【权利要求摘要】
{json.dumps(draft.get("claims", {}), ensure_ascii=False)[:1800]}

【严格要求】
1. 必须由你调用 `patent_drawing_generator` 生成每一个缺失图号对应的附图。
2. 每张图的 `description` 必须是该图具体绘图内容，不能为空，不能只写“图X为……示意图”。
3. 每张图必须主题不同，不能只换标题而复用相同内容。
4. 图号、标题、说明必须与专利草稿一致。
5. 不要生成最终 DOCX。
6. 最终只输出严格 JSON：
{{
  "drawings": [
    {{
      "figure_number": "图1",
      "title": "当前草稿中该图的真实附图标题",
      "description": "当前草稿中该图必须表达的具体对象、结构、步骤、连接关系或状态变化。",
      "file_path": "/absolute/path/to/figure.png",
      "artifact_url": "/api/v1/workflows/{context.task_id}/artifacts/...",
      "mime_type": "image/png"
    }}
  ]
}}"""
            agent_result = await asyncio.wait_for(
                _run_agent_conversation(
                    profile_id="patent.writer.v1",
                    prompt=agent_prompt,
                    session_id=f"{context.task_id}:patent_drawing_repair",
                    timeout_seconds=WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS,
                ),
                timeout=WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS,
            )
            parsed: Dict[str, Any] = {}
            if isinstance(agent_result, dict):
                parsed = self._try_parse_json(
                    agent_result.get("structured_result")
                    or agent_result.get("final_response")
                    or agent_result.get("response")
                    or agent_result
                )
            else:
                parsed = self._try_parse_json(agent_result)
            generated_drawings = [
                item for item in (parsed.get("drawings") or [])
                if isinstance(item, dict)
            ]

            if generated_drawings:
                existing = draft.get("drawings", [])
                if not isinstance(existing, list):
                    existing = []
                draft["drawings"] = self._normalize_drawing_metadata(
                    [*existing, *generated_drawings],
                    planned_specs=planned_specs,
                )
                draft["drawings_generated_by"] = "patent_writer_agent"
                if event_callback:
                    event_callback(
                        "专利撰写 Agent",
                        "agent.content",
                        f"✅ 撰写 Agent 已生成/补齐 {len(generated_drawings)} 张专利附图",
                        {
                            "agent_name": "专利撰写 Agent",
                            "content": json.dumps(generated_drawings, ensure_ascii=False),
                            "phase": "patent_writing",
                        },
                    )
        except Exception as exc:
            self._logger.warning(f"Failed to generate required patent drawings: {exc}")
            draft.setdefault("_drawing_generation_error", str(exc)[:500])
            if self._missing_drawing_references(draft):
                draft["_agent_failed"] = True
                draft["_agent_error"] = (
                    "专利撰写 Agent 未能在限定时间内补齐必要附图；"
                    "需要 CEO 继续调度撰写 Agent 基于现有草稿和附图反馈补齐。"
                )

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
                title=draft.get("title") or draft.get("patent_title") or context.title,
                claims=draft.get("claims", {}),
                description=draft.get("description", {}),
                abstract=draft.get("abstract", ""),
                task_id=context.task_id,
                tech_description=self._build_confirmed_writer_context(context, limit=12000),
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
        """Attach reviewer feedback and deterministic formatting before re-review.

        The workflow engine must not synthesize patent substance locally. Subjective
        remediation belongs to the responsible Hermes Agent via its LLM; this method only
        preserves the current draft, normalizes objective formatting, and records what the
        CEO needs to route back into the loop.
        """
        if not isinstance(draft, dict):
            draft = {}
        repaired = dict(draft)
        claims = repaired.get("claims")
        if isinstance(claims, dict):
            repaired["claims"] = normalize_claims_payload_linebreaks(claims)

        repaired["drawings"] = self._normalize_drawing_metadata(
            repaired.get("drawings", []),
            planned_specs=self._planned_drawing_specs(repaired),
        )
        repaired["_remediation_required"] = {
            "round": context.iteration_count,
            "source": "quality_review_suggestions",
            "issues": review_issues[:12],
            "required_action": (
                "CEO must dispatch the responsible Hermes Agent to revise patent substance; "
                "the workflow engine only normalizes objective formatting."
            ),
        }
        repaired["_needs_agent_rewrite"] = True

        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.content",
                "🧭 已汇总审查问题，继续调度对应 Agent 修复",
                {
                    "agent_name": "CEO Agent",
                    "phase": "patent_writing",
                    "content": json.dumps(repaired.get("_remediation_required"), ensure_ascii=False),
                },
            )
        return repaired

    def _merge_reusable_revision_drawings(
        self,
        context: WorkflowContext,
        draft: Dict[str, Any],
        review_issues: List[str],
    ) -> Dict[str, Any]:
        """Preserve usable drawings across writer revision rounds.

        Revision rounds should build on the previous draft. If the writer returns
        only changed text and omits unchanged drawing metadata, the workflow must
        not treat every prior figure as missing and regenerate them. Figures
        explicitly mentioned in review feedback remain eligible for regeneration.
        """
        if not isinstance(draft, dict):
            return draft
        previous = context.patent_draft if isinstance(context.patent_draft, dict) else {}
        previous_drawings = previous.get("drawings") if isinstance(previous, dict) else []
        current_drawings = draft.get("drawings") if isinstance(draft.get("drawings"), list) else []
        if not isinstance(previous_drawings, list) or not previous_drawings:
            return draft

        issue_text = "\n".join(str(issue or "") for issue in review_issues)
        mentioned_figures = {
            f"图{number}" for number in re.findall(r"图\s*([0-9]{1,2})", issue_text)
        }
        planned_specs = self._planned_drawing_specs(draft)
        current_by_number: Dict[str, Dict[str, Any]] = {}
        for item in current_drawings:
            if not isinstance(item, dict):
                continue
            number = str(item.get("figure_number") or "").replace(" ", "")
            if re.fullmatch(r"图\d+", number):
                current_by_number[number] = dict(item)

        merged = list(current_by_number.values())
        existing_numbers = set(current_by_number)
        for item in previous_drawings:
            if not isinstance(item, dict):
                continue
            number = str(item.get("figure_number") or "").replace(" ", "")
            if not re.fullmatch(r"图\d+", number):
                continue
            if number in existing_numbers or number in mentioned_figures:
                continue
            if not self._drawing_artifact_is_accessible(item):
                continue
            merged_item = dict(item)
            merged.append(merged_item)
            existing_numbers.add(number)

        if len(merged) != len(current_drawings):
            draft["drawings"] = self._normalize_drawing_metadata(
                merged,
                planned_specs=planned_specs,
            )
            draft["_reused_revision_drawings"] = sorted(
                {
                    str(item.get("figure_number") or "").replace(" ", "")
                    for item in draft.get("drawings", [])
                    if isinstance(item, dict)
                    and self._drawing_artifact_is_accessible(item)
                    and str(item.get("figure_number") or "").replace(" ", "") not in current_by_number
                }
            )
        return draft

    def _normalize_drawing_metadata(
        self,
        drawings: object,
        planned_specs: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(drawings, list):
            return []
        if planned_specs is None:
            planned_specs = []
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
            final_title = title_map.get(figure_number) or raw_title
            if not final_title:
                continue
            drawing["title"] = final_title
            drawing["description"] = description_map.get(figure_number) or str(drawing.get("description") or "").strip()
            normalized.append(drawing)
        return normalized

    def _apply_patent_manual_normalization(
        self,
        draft: Dict[str, Any],
        context_title: str = "",
    ) -> Dict[str, Any]:
        """Apply deterministic manual rules and attach objective compliance signals."""
        if not isinstance(draft, dict):
            return draft
        normalized = dict(draft)
        if not str(normalized.get("title") or normalized.get("patent_title") or "").strip():
            confirmed_title = str(context_title or "").strip()
            if confirmed_title:
                normalized["title"] = confirmed_title
                normalized["patent_title"] = confirmed_title
        claims = normalized.get("claims") or {}
        if isinstance(claims, dict):
            normalized["claims"] = normalize_claims_payload_linebreaks(claims)

        drawings = normalized.get("drawings") or []
        if isinstance(drawings, list):
            normalized["drawings"] = self._normalize_drawing_metadata(
                drawings,
                planned_specs=self._planned_drawing_specs(normalized),
            )

        claim_report = validate_claim_rules(normalized.get("claims", {}))
        document_report = validate_patent_document_structure(
            build_patent_text_from_draft(normalized),
            drawings=normalized.get("drawings", []) if isinstance(normalized.get("drawings"), list) else [],
        )
        manual_draft_report = validate_patent_manual_draft(normalized)
        normalized["manual_compliance"] = {
            "claim_rules": claim_report,
            "document_rules": document_report,
            "manual_draft_rules": manual_draft_report,
            "high_priority_issues": collect_high_priority_issues(
                claim_report,
                document_report,
                manual_draft_report,
            ),
        }
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

        claim_report = validate_claim_rules(claims)
        for issue in claim_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"claim_rule:{issue.get('issue', '')}")

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

        document_report = validate_patent_document_structure(
            build_patent_text_from_draft(draft),
            drawings=draft.get("drawings", []) if isinstance(draft.get("drawings"), list) else [],
        )
        for issue in document_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"document_rule:{issue.get('issue', '')}")

        manual_draft_report = validate_patent_manual_draft(draft)
        for issue in manual_draft_report.get("issues", []):
            if issue.get("severity") in {"critical", "high"}:
                issues.append(f"manual_rule:{issue.get('issue', '')}")

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
        """Clear stale failure flags after the writer Agent has produced reviewable content.

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
        repaired["_writer_agent_recovered"] = True
        return repaired

    def _merge_manual_compliance_into_review(
        self,
        context: WorkflowContext,
        review_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge deterministic manual-rule findings into the reviewer report.

        The quality reviewer remains responsible for professional judgment, but
        hard rules from the drafting manual cannot be ignored when generating
        the workflow decision.
        """
        if not isinstance(review_report, dict):
            review_report = {}
        draft = (
            self._apply_patent_manual_normalization(
                context.patent_draft,
                context_title=context.title,
            )
            if isinstance(context.patent_draft, dict)
            else {}
        )
        if draft:
            context.patent_draft = draft
        manual = draft.get("manual_compliance", {}) if isinstance(draft, dict) else {}
        claim_report = manual.get("claim_rules", {}) if isinstance(manual, dict) else {}
        doc_report = manual.get("document_rules", {}) if isinstance(manual, dict) else {}
        draft_report = manual.get("manual_draft_rules", {}) if isinstance(manual, dict) else {}

        def to_review_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
            target_agent = str(issue.get("target_agent") or "patent_writer")
            if target_agent in {"retrieval_analyst", "retrieval", "search"}:
                responsible_phase = "retrieval_analysis"
            elif target_agent in {"requirement_analyst", "requirement", "brainstorm_partner"}:
                responsible_phase = "requirement_analysis"
            else:
                responsible_phase = "patent_writing"
            return {
                "severity": issue.get("severity", "medium"),
                "location": issue.get("location", "全文"),
                "description": issue.get("issue") or issue.get("description", ""),
                "suggestion": issue.get("suggestion", ""),
                "target_agent": target_agent,
                "responsible_phase": responsible_phase,
                "source": "deterministic_manual_gate",
            }

        claim_issues = [
            to_review_issue(item)
            for item in claim_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        doc_issues = [
            to_review_issue(item)
            for item in doc_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        draft_issues = [
            to_review_issue(item)
            for item in draft_report.get("issues", [])
            if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
        ]
        if not claim_issues and not doc_issues and not draft_issues:
            return review_report

        merged = dict(review_report)
        merged["_hard_rule_failed"] = True
        all_hard_issues = claim_issues + doc_issues + draft_issues
        hard_routes = {
            str(issue.get("responsible_phase") or "")
            for issue in all_hard_issues
            if str(issue.get("responsible_phase") or "")
        }
        if "retrieval_analysis" in hard_routes:
            merged["_hard_rule_route"] = "retrieval_analysis"
            merged["root_cause"] = "evidence_missing"
        elif "requirement_analysis" in hard_routes:
            merged["_hard_rule_route"] = "requirement_analysis"
            merged["root_cause"] = "requirement_unclear"
        else:
            merged["_hard_rule_route"] = "patent_writing"
            merged.setdefault("root_cause", "content_incomplete")

        claims_review = dict(merged.get("claims_review") or {})
        claims_review.setdefault("issues", [])
        if isinstance(claims_review["issues"], list):
            claims_review["issues"].extend(claim_issues)
        merged["claims_review"] = claims_review

        formal_review = dict(merged.get("formal_compliance_review") or {})
        formal_review.setdefault("issues", [])
        if isinstance(formal_review["issues"], list):
            formal_review["issues"].extend(doc_issues + draft_issues)
        merged["formal_compliance_review"] = formal_review

        drawing_issues = [
            issue for issue in doc_issues
            if "图" in str(issue.get("location", "")) or "附图" in str(issue.get("location", ""))
        ]
        if drawing_issues:
            drawing_review = dict(merged.get("drawing_review") or {})
            drawing_review.setdefault("issues", [])
            if isinstance(drawing_review["issues"], list):
                drawing_review["issues"].extend(drawing_issues)
            merged["drawing_review"] = drawing_review

        merged["manual_compliance"] = manual
        return merged

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

    def _analyze_workflow_failure(self, context: WorkflowContext) -> Dict[str, Any]:
        """Build a deterministic failure report for CEO routing.

        CEO only reports contracts, Agent failures, and review Agent findings.
        It does not create specialist patent conclusions or content advice.
        """
        issues: List[Dict[str, str]] = []
        suggestions: List[str] = []

        draft_contract_issues = self._validate_phase_contract("patent_draft", context.patent_draft)
        review_contract_issues = self._validate_phase_contract("review_report", context.review_report)

        draft = context.patent_draft if isinstance(context.patent_draft, dict) else {}
        review = context.review_report if isinstance(context.review_report, dict) else {}

        if draft_contract_issues:
            for issue in draft_contract_issues:
                issues.append({
                    "type": "patent_draft_contract",
                    "message": issue,
                    "severity": "critical",
                })
            suggestions.append("路由回专利撰写 Agent，基于上一轮草稿和反馈补齐专利草稿结构契约。")

        if draft.get("_agent_failed") is True:
            issues.append({
                "type": "patent_writer_failed",
                "message": str(draft.get("_agent_error") or "专利撰写 Agent 执行失败。")[:500],
                "severity": "critical",
            })
            suggestions.append("路由回专利撰写 Agent，携带失败输出和错误信息继续修正。")

        if review_contract_issues:
            for issue in review_contract_issues:
                issues.append({
                    "type": "review_report_contract",
                    "message": issue,
                    "severity": "critical",
                })
            suggestions.append("路由回质量审查 Agent，要求按审查输出契约补齐 recommendation、review_summary、root_cause 和 responsible_phase。")

        if review.get("_agent_failed") is True:
            issues.append({
                "type": "quality_reviewer_failed",
                "message": str(review.get("_agent_error") or "质量审查 Agent 执行失败。")[:500],
                "severity": "critical",
            })
            suggestions.append("路由回质量审查 Agent，携带专利草稿摘要重新审查。")

        if self._needs_quality_remediation(review):
            route = self._classify_remediation_path(review, context)
            route_display = {
                "WRITE_MORE": "专利撰写 Agent",
                "ANALYZE_MORE": "需求分析 Agent",
                "SEARCH_MORE": "检索分析 Agent",
                "NEEDS_USER_INPUT": "用户补充信息",
                "TERMINAL_FAILURE": "终止并展示不可自动恢复原因",
            }.get(route, "专利撰写 Agent")
            for issue in self._extract_review_issue_records(review)[:10]:
                description = str(
                    issue.get("description")
                    or issue.get("reason")
                    or issue.get("message")
                    or issue.get("risk_type")
                    or issue.get("section")
                    or "质量审查 Agent 标记的问题"
                )
                severity = str(issue.get("severity") or issue.get("likelihood") or "high")
                issues.append({
                    "type": str(issue.get("section") or "quality_review_issue"),
                    "message": description[:500],
                    "severity": severity if severity in {"low", "medium", "high", "critical"} else "high",
                })
            suggestions.append(f"按质量审查 Agent 的 root_cause/responsible_phase 路由到：{route_display}。")

        if draft_contract_issues or draft.get("_agent_failed") is True:
            phase = "patent_writing"
            phase_display = "专利撰写阶段"
            main_reason = "专利撰写阶段输出未满足阶段契约"
        elif review_contract_issues or review.get("_agent_failed") is True or self._needs_quality_remediation(review):
            phase = "quality_review"
            phase_display = "质量审查阶段"
            main_reason = "质量审查阶段输出未通过或未满足阶段契约"
        else:
            phase = "final_check"
            phase_display = "最终检查阶段"
            main_reason = "最终检查发现仍存在未解决契约问题"

        if not issues:
            issues.append({
                "type": "unresolved_contract",
                "message": "工作流存在未解决问题，但当前阶段未提供可路由的结构化缺陷。",
                "severity": "critical",
            })
            suggestions.append("路由回质量审查 Agent，要求输出结构化缺陷和 responsible_phase。")

        return {
            "phase": phase,
            "phase_display": phase_display,
            "main_reason": main_reason,
            "issues": issues,
            "suggestions": list(dict.fromkeys(suggestions)),
        }

    def _review_requires_drawing_changes(self, review_report: Dict[str, Any]) -> bool:
        """Return True only when review feedback specifically requires drawing changes."""
        if not isinstance(review_report, dict):
            return False
        drawing_terms = (
            "附图",
            "图号",
            "图题",
            "插图",
            "图片",
            "图文",
            "draw",
            "figure",
        )
        actionable_terms = (
            "缺失",
            "损坏",
            "不可访问",
            "重复",
            "不一致",
            "不符",
            "错误",
            "重画",
            "重新生成",
            "替换",
            "补齐",
            "新增",
        )
        concrete_drawing_problem_terms = (
            "缺失",
            "损坏",
            "不可访问",
            "重复",
            "图文不符",
            "图文不一致",
            "图号重复",
            "未生成",
            "无法访问",
            "无法打开",
            "需要重画",
            "重新生成",
            "替换图",
            "补齐图",
            "新增图",
        )
        for record in self._extract_review_issue_records(review_report):
            section = str(record.get("section") or "").lower()
            text = " ".join(
                str(record.get(key) or "")
                for key in ("location", "description", "suggestion", "reason", "suggested_content")
            ).lower()
            if not text:
                continue
            has_drawing_reference = any(term.lower() in text for term in drawing_terms) or any(
                key in section for key in ("drawing", "figure")
            )
            if not has_drawing_reference:
                continue
            if "最终docx" in text and "复核" in text and not any(
                term in text for term in ("缺", "损坏", "不可访问", "重复", "不符", "不一致")
            ):
                continue
            has_concrete_figure = bool(re.search(r"图\s*[0-9]{1,2}", text, re.IGNORECASE))
            has_concrete_problem = any(term.lower() in text for term in concrete_drawing_problem_terms)
            if has_concrete_problem and (
                has_concrete_figure
                or "附图缺失" in text
                or "未生成附图" in text
                or "drawing" in section
                or "figure" in section
            ):
                return True
        return False

    def _build_revision_prompt(
        self,
        context: WorkflowContext,
        review_issues: List[str],
        allow_drawing_generation: bool = True,
    ) -> str:
        """构建修正撰写的prompt，包含审查问题和原有草稿"""
        draft_output = self._latest_phase_output(context, WorkflowPhase.WRITING, "patent_draft")
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        current_draft = draft_output or context.patent_draft
        draft_summary = json.dumps(current_draft, ensure_ascii=False)[:6000]
        previous_drawings = []
        if isinstance(current_draft, dict):
            previous_drawings = [
                item for item in (current_draft.get("drawings") or [])
                if isinstance(item, dict)
            ]
        previous_drawings_summary = json.dumps(previous_drawings, ensure_ascii=False)[:3000]
        drawing_revision_rule = (
            "审查意见明确涉及附图缺失、损坏、重复、图文不符或附图实施例变化；仅允许针对被点名的图号重新调用生图工具。"
            if allow_drawing_generation
            else "本轮审查未指出附图缺失、损坏、重复或图文不符；禁止调用 patent_drawing_generator，必须原样返回上一轮可访问附图元数据。"
        )
        requirement_summary = json.dumps(requirement_output, ensure_ascii=False)[:3000]
        retrieval_summary = self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )
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
当前专利文件不能作为修正依据。请以已确认撰写上下文、需求分析结果和检索分析结果为主要依据，重新生成完整专利文件。"""

        return f"""请基于质量审查意见对专利申请文件进行修正。

## 审查发现的问题（必须全部解决）：
{issues_text}
{failed_hint}

## 已确认撰写上下文：
{confirmed_writer_context}

## 需求分析结果：
{requirement_summary}

## 检索分析结果：
{retrieval_summary}

## 当前专利文件：
{draft_summary}

## 上一轮可复用附图元数据：
{previous_drawings_summary}

## 修正要求：
1. 这是基于上一轮专利文件的迭代修正，不是重新开始；上一轮已正确且未被指出问题的内容必须保留
2. 逐一解决上述所有问题；仅替换或补充需要修复的权利要求、说明书章节、摘要或附图
3. 如果需求分析或检索报告中已有明确结论，不得丢弃；如确需调整，必须与审查问题直接相关
4. 保持原有文件结构不变（权利要求书+说明书+摘要+必要附图）
5. 修正后输出完整的JSON格式专利文件，而不是只输出修改片段
6. 确保修改后权利要求与说明书、附图的一致性
7. 如果审查问题涉及背景技术或证据，背景技术必须按三段式重写，并点名引用至少两个检索报告 confirmed_sources / web_evidence / non_patent_prior_art 中的真实来源标题、论文号、公开资料名称或 URL；不得只写“公开技术”“相关研究”等泛称，不得虚构专利号
8. 若发明名称、摘要或发明内容包含“方法及系统”或“系统”，权利要求书必须包含对应系统独立权利要求；系统独权应以模块/单元承接权利要求1的方法步骤。若不增加系统独权，必须把发明名称、摘要和发明内容统一改为只保护“方法”。
9. 权利要求1仍必须只能由S1-S3或S1-S4组成，且不超过250字；系统独立权利要求不计入权利要求1步数，但必须与说明书系统结构一致。
10. 修订轮不得重画或替换未被审查指出问题且文件可访问的附图；必须原样返回上一轮可复用附图元数据。只有审查意见明确指出某张图缺失、损坏、重复、图文不符或该图实施例需要改变时，才重新调用生图工具生成该图。
   - 当前附图修订判定：{drawing_revision_rule}
11. 具体实施方式不得截断；必须显式按权利要求1的 S1、S2、S3（以及 S4，如有）逐项展开；所有被审查指出的图号对应实施例必须完整补齐，不能以“补充……”或省略号结束。"""

    def _build_retrieval_summary_for_writer(self, retrieval_output: Any, limit: int = 12000) -> str:
        """Build a source-preserving retrieval summary for the writer Agent.

        This is only context packaging. It does not add evidence, invent sources,
        or make patentability judgments.
        """
        if not isinstance(retrieval_output, dict) or not retrieval_output:
            return "{}"
        keys = (
            "retrieval_strategy",
            "confirmed_sources",
            "prior_art_references",
            "similar_patents",
            "web_evidence",
            "non_patent_prior_art",
            "evidence_sources",
            "evidence_gaps",
            "novelty_assessment",
            "inventive_step_assessment",
            "utility_assessment",
            "writing_recommendations",
            "risk_factors",
            "overall_patentability",
            "overall_confidence",
            "conclusion",
        )
        compact = {key: retrieval_output.get(key) for key in keys if retrieval_output.get(key) not in (None, "", [])}
        return json.dumps(compact or retrieval_output, ensure_ascii=False, default=str)[:limit]

    def _build_confirmed_writer_context(
        self,
        context: WorkflowContext,
        requirement_output: Any = None,
        retrieval_output: Any = None,
        limit: int = 16000,
    ) -> str:
        """Build the writer-facing technical package from confirmed workflow facts.

        Raw transcript wrappers are excluded here. The writer still receives the
        sanitized source disclosure so revision rounds can preserve original
        technical facts while avoiding timestamps, speaker labels and meeting
        formatting artifacts.
        """
        shared = context.shared_agent_context if isinstance(context.shared_agent_context, dict) else {}
        safe_shared = {
            key: value
            for key, value in shared.items()
            if key
            not in {
                "user_supplements",
                "raw_disclosure",
                "original_description",
                "disclosure_text",
                "transcript",
            }
        }
        sanitized_source_disclosure = self._sanitize_disclosure_text(
            context.original_description or str(context.metadata.get("raw_disclosure") or "")
        )
        payload = {
            "task_id": context.task_id,
            "patent_title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
            "target_country": context.target_country,
            "patent_type_preference": context.metadata.get("patent_type_preference", ""),
            "confirmed_preflight": context.metadata.get("confirmed_preflight", {}),
            "sanitized_source_disclosure": sanitized_source_disclosure[:6000],
            "shared_confirmed_facts": safe_shared,
            "requirement_analysis": requirement_output or self._latest_phase_output(
                context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
            ),
            "retrieval_report": self._build_retrieval_summary_for_writer(
                retrieval_output
                if retrieval_output is not None
                else self._latest_phase_output(context, WorkflowPhase.RETRIEVAL, "retrieval_report"),
                limit=12000,
            ),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)[:limit]

    async def _generate_patent_in_sections(
        self,
        service,
        profile_id: str,
        base_task: str,
        context,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
        allow_drawing_generation: bool = True,
    ) -> Dict[str, Any]:
        """通过 Agent 工具调用生成专利文件
        
        Agent 会按照 SOUL.md 中定义的工具调用序列：
        1. claim_drafter - 获取权利要求撰写骨架和客观约束
        2. description_writer - 获取说明书章节约束和客观提示
        3. support_checker - 检查支持关系  
        4. patent_drawing_generator - 由撰写 Agent 生成必要附图
        正式专利正文由 Agent LLM 生成，最终 .docx 在质量审查通过后生成。
        
        返回前端期望的结构化 dict。
        """
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        req_data = json.dumps(requirement_output, ensure_ascii=False)[:2000] if requirement_output else ""
        ret_data = self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )
        reusable_drawings = []
        if not allow_drawing_generation and isinstance(context.patent_draft, dict):
            reusable_drawings = [
                item for item in (context.patent_draft.get("drawings") or [])
                if isinstance(item, dict) and self._drawing_artifact_is_accessible(item)
            ]
        reusable_drawings_json = json.dumps(reusable_drawings, ensure_ascii=False)[:5000]
        drawing_task_rule = (
            """3. 对涉及结构、装置、系统、流程或空间关系的发明，调用 patent_drawing_generator 工具生成对应附图
    - tech_description: 依据权利要求、说明书附图说明和原始技术方案整理的绘图说明
    - task_id: 当前工作流任务ID {task_id}
    - title: 当前草稿中该图的真实附图标题
    - description: 当前草稿中该图必须表达的具体对象、结构、步骤、连接关系或状态变化"""
        ).format(task_id=context.task_id) if allow_drawing_generation else f"""3. 本轮是文字/权利要求修订，审查未要求修图，禁止调用 patent_drawing_generator。
    - 必须复用并原样返回以下上一轮可访问附图元数据。
    - 只有下一轮质量审查明确指出某张图缺失、损坏、重复、图文不符或附图实施例需要改变时，才允许重画。
    - 上一轮可复用附图元数据：
{reusable_drawings_json}"""
        task_context = str(base_task or "").strip()
        tech_content = "\n\n".join(
            part
            for part in [
                f"当前撰写任务/修正要求：\n{task_context}" if task_context else "",
                "已确认撰写上下文：\n" + confirmed_writer_context,
                json.dumps(requirement_output or {}, ensure_ascii=False),
                ret_data,
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
            timeout_seconds: int = 75,
        ) -> Dict[str, Any]:
            """Run a writer-owned tool with progress events and a bounded wait.

            Section drafting must be real: a slow or failed LLM/tool call should be
            surfaced as a writer failure instead of being replaced by local content.
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
                        f"⚠️ {tool_name} 调用超时或失败，停止本轮撰写并等待 CEO 重新调度",
                        {
                            "agent_name": "专利撰写 Agent",
                            "thought": "writer_tool_failed",
                            "tool_name": tool_name,
                            "error": result["error"],
                        },
                    )
                return result

        # Patent writing stays inside the Hermes Agent loop. The workflow engine only
        # builds context, captures tool events, and parses the Agent's final JSON.
        
        # 构建完整的专利撰写任务 prompt，让 Agent 通过工具调用完成
        # 注：不在此阶段生成 docx，待质量审查通过后再生成
        task_prompt = f"""请基于以下技术方案，通过调用工具生成完整的专利申请文件内容。

【发明名称】
{context.title or "待定"}

【已确认技术方案上下文】
{confirmed_writer_context}

【需求分析结果】
{req_data}

【检索分析结果】
{ret_data}

【任务要求】
请按顺序调用 Hermes 工具获取结构、约束、客观信号和附图产物；正式专利正文必须由你作为专利撰写 Agent 通过 LLM 判断并生成：

1. 调用 claim_drafter 工具获取权利要求撰写骨架
   - features: 从技术描述中提取的技术特征
   - protection_scope: 期望的保护范围
   - 注意：工具只返回骨架/特征顺序，正式权利要求由你生成
   - 硬性规范：权利要求书由独权和从权组成；权利要求1只能写成3步或4步且不超过250字；每个分号“；”和句号“。”后必须换行。
   - 如果发明名称、发明内容或保护范围包含“方法及系统”或“系统”，必须同时撰写方法独立权利要求和系统独立权利要求；系统独权应以模块/单元承接权利要求1的方法步骤。若只保护方法，则发明名称、摘要和发明内容不能写“系统”。
   
2. 调用 description_writer 工具获取说明书各章节写作约束
   - section_type="technical_field": 技术领域
   - section_type="background": 背景技术
   - section_type="summary": 发明内容（技术问题+技术方案+有益效果）
   - section_type="detailed": 具体实施方式
   - 注意：工具只返回章节约束，正式说明书正文由你生成
   
 {drawing_task_rule}

 4. 调用 support_checker 检查你生成的权利要求与说明书的支持关系

注意：本阶段仅生成专利内容和必要附图，不生成最终文档文件。请确保所有内容完整、规范。
【专利规范硬性要求】
- 不得把交底逐字稿中的时间戳、说话人、会议口语或格式性内容写入正文。
- 说明书摘要必须包含：专利名称、技术领域、简化技术方案、技术效果，且不超过300字。
- 技术领域必须具体，不能写成发明本身，也不能混入方案细节。
	- 背景技术必须基于检索报告中的真实现有技术，并避免泄露本发明的具体方案；必须点名引用至少两个 confirmed_sources / web_evidence / non_patent_prior_art 中的真实来源标题、论文号、公开资料名称或 URL，例如 arXiv 论文、Microsoft Research 项目页、官方公开资料等，并说明这些来源没有解决的具体技术问题。不得只写“公开技术”“相关研究”等泛称，不得虚构专利号。
- 发明内容必须包含技术问题、技术方案、有益效果，三者一一对应。
- 附图至少按需要规划4幅；每幅图必须表达不同主题，不能只换标题或重复图片内容。
- 附图说明不得重复图号或重复标题。
- 具体实施方式必须与权利要求和附图对应，不能使用 Markdown 标题。
- 具体实施方式必须显式按权利要求1的 S1、S2、S3（以及 S4，如有）逐项展开，不能缺少步骤编号。
- 如果题名为“方法及系统”或正文包含系统保护主题，权利要求书中必须出现对应系统独立权利要求，不能只在说明书中描述系统。
最终只输出严格 JSON，不要输出 Markdown、代码块或解释文字：
{{
  "claims": {{
    "independent_claim": "1. ...",
    "dependent_claims": ["2. ..."]
  }},
  "description": {{
    "technical_field": "...",
    "background_art": "...",
    "summary_of_invention": "...",
    "description_of_drawings": "...",
    "detailed_description": "..."
  }},
  "abstract": "...",
  "drawings": []
}}

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
        drawings_data = list(reusable_drawings)
        final_response = ""
        last_failed_result: Optional[Dict[str, Any]] = None

        def _preview(value: Any, limit: int = 220) -> str:
            text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
            return text[:limit] + ("..." if len(text) > limit else "")

        def _emit_writer_section_result(
            section_key: str,
            section_label: str,
            content: Any,
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            if not event_callback:
                return
            preview = _preview(content)
            event_callback(
                "专利撰写 Agent",
                "agent.content",
                f"📝 {section_label}已生成" + (f"：{preview}" if preview else ""),
                {
                    "agent_name": "专利撰写 Agent",
                    "phase": "patent_writing",
                    "section": section_key,
                    "section_label": section_label,
                    "content_preview": preview,
                    **(extra or {}),
                },
            )

        for writer_attempt in range(3):
            agent_result = await _run_agent_conversation_with_timeout(
                profile_id,
                task_prompt,
                timeout_seconds=_configured_timeout_seconds(
                    "writer_initial_timeout_seconds",
                    WRITER_INITIAL_TIMEOUT_SECONDS,
                ),
            )

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
                            if claims_count:
                                _emit_writer_section_result(
                                    "claims",
                                    "权利要求书",
                                    claims_data.get("independent_claim", ""),
                                    {"claims_count": claims_count},
                                )

                        elif tool_name == "description_writer" and tool_content.get("success"):
                            section_type = tool_data.get("section_type", "")
                            content = tool_data.get("content", "")
                            section_label = {
                                "technical_field": "技术领域",
                                "background": "背景技术",
                                "summary": "发明内容",
                                "drawings": "附图说明",
                                "drawings_description": "附图说明",
                                "detailed": "具体实施方式",
                            }.get(str(section_type), str(section_type) or "说明书章节")
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
                            if content:
                                _emit_writer_section_result(
                                    f"description.{section_type}",
                                    section_label,
                                    content,
                                )

                        elif tool_name == "patent_docx_generator" and tool_content.get("success"):
                            docx_path = tool_data.get("file_path", "")
                            abstract_text = tool_data.get("abstract", "") or abstract_text
                            self._logger.info(f"DOCX generated: {docx_path}")
                            if abstract_text:
                                _emit_writer_section_result("abstract", "说明书摘要", abstract_text)

                        elif (
                            tool_name == "patent_drawing_generator"
                            and tool_content.get("success")
                            and allow_drawing_generation
                        ):
                            drawings = tool_data.get("drawings", [])
                            if isinstance(drawings, list):
                                drawings_data.extend(item for item in drawings if isinstance(item, dict))
                            self._logger.info(f"Got patent drawings: {len(drawings_data)} drawings")
                            if drawings_data:
                                titles = [
                                    str(item.get("figure_number") or item.get("title") or "").strip()
                                    for item in drawings_data
                                    if isinstance(item, dict)
                                ]
                                _emit_writer_section_result(
                                    "drawings",
                                    "附图清单",
                                    "、".join(title for title in titles if title),
                                    {"drawing_count": len(drawings_data)},
                                )

                    except (json.JSONDecodeError, KeyError) as e:
                        self._logger.warning(f"Failed to parse tool result: {e}")
                        continue

            agent_structured_output: Dict[str, Any] = {}
            if isinstance(agent_result, dict):
                candidate = agent_result.get("structured_result")
                if isinstance(candidate, dict):
                    agent_structured_output = candidate
            if not agent_structured_output:
                parsed_final = self._try_parse_json(final_response)
                if isinstance(parsed_final, dict) and "raw_output" not in parsed_final:
                    agent_structured_output = parsed_final

            if isinstance(agent_structured_output, dict):
                candidate_claims = agent_structured_output.get("claims")
                if isinstance(candidate_claims, dict):
                    normalized_claims = self._normalize_claims_payload(candidate_claims)
                    if normalized_claims.get("independent_claim"):
                        claims_data = normalized_claims
                        _emit_writer_section_result(
                            "claims",
                            "权利要求书",
                            normalized_claims.get("independent_claim", ""),
                            {
                                "claims_count": 1 + len(normalized_claims.get("dependent_claims") or []),
                                "source": "agent_final_json",
                            },
                        )

                candidate_description = agent_structured_output.get("description")
                if isinstance(candidate_description, dict):
                    for source_key, target_key in (
                        ("technical_field", "technical_field"),
                        ("background_art", "background_art"),
                        ("summary_of_invention", "summary_of_invention"),
                        ("description_of_drawings", "drawings_description"),
                        ("drawings_description", "drawings_description"),
                        ("detailed_description", "detailed_description"),
                    ):
                        value = candidate_description.get(source_key)
                        if isinstance(value, str) and value.strip():
                            description_data[target_key] = value.strip()
                            section_label = {
                                "technical_field": "技术领域",
                                "background_art": "背景技术",
                                "summary_of_invention": "发明内容",
                                "drawings_description": "附图说明",
                                "detailed_description": "具体实施方式",
                            }.get(target_key, "说明书章节")
                            _emit_writer_section_result(
                                f"description.{target_key}",
                                section_label,
                                value,
                                {"source": "agent_final_json"},
                            )

                if isinstance(agent_structured_output.get("abstract"), str):
                    abstract_text = agent_structured_output["abstract"].strip() or abstract_text
                    if abstract_text:
                        _emit_writer_section_result(
                            "abstract",
                            "说明书摘要",
                            abstract_text,
                            {"source": "agent_final_json"},
                        )

                candidate_drawings = agent_structured_output.get("drawings")
                if isinstance(candidate_drawings, list):
                    candidate_drawing_items = [
                        item for item in candidate_drawings if isinstance(item, dict)
                    ]
                    if allow_drawing_generation or candidate_drawing_items:
                        drawings_data = candidate_drawing_items
                    if drawings_data:
                        _emit_writer_section_result(
                            "drawings",
                            "附图清单",
                            "、".join(
                                str(item.get("figure_number") or item.get("title") or "").strip()
                                for item in drawings_data
                                if isinstance(item, dict)
                            ),
                            {"drawing_count": len(drawings_data), "source": "agent_final_json"},
                        )

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
            repaired = await self._repair_incomplete_patent_draft_with_agent(
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
        
        # 如果 Hermes 工具调用和 Agent 结构化 JSON 都没有返回专利内容，明确失败。
        # 不再从文本中的 <tool_call> 片段伪造工具结果；工具必须由 Agent 真实调用。
        if not claims_data and not description_data:
            self._logger.warning(
                "Patent writer produced no structured Hermes tool or JSON result; marking draft incomplete"
            )
            return {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": "专利撰写 Agent 未返回可解析的结构化专利文件，不能由本地文本解析或伪造工具结果替代。",
                "claims": {"independent_claim": "", "dependent_claims": []},
                "description": {
                    "technical_field": "",
                    "background_art": "",
                    "summary_of_invention": "",
                    "drawings_description": "",
                    "detailed_description": "",
                },
                "abstract": "",
                "drawings": drawings_data,
                "docx_path": "",
                "full_response": final_response,
            }
        
        # 组装为前端期望的结构化格式（不含 docx，待质量审查通过后生成）
        patent_result: Dict[str, Any] = {
            "title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
            "patent_title": context.title or context.metadata.get("confirmed_preflight", {}).get("patent_title", ""),
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
        patent_result = self._apply_patent_manual_normalization(
            patent_result,
            context_title=context.title,
        )

        claims_count = 1 + len(patent_result["claims"]["dependent_claims"]) if patent_result["claims"]["independent_claim"] else 0
        sections_count = sum(1 for v in patent_result["description"].values() if v)
        self._logger.info(f"Patent writer: content generated. Claims={claims_count}, Sections={sections_count} (DOCX deferred to post-review)")

        return patent_result

    async def _repair_incomplete_patent_draft_with_agent(
        self,
        context: WorkflowContext,
        claims_data: Dict[str, Any],
        description_data: Dict[str, Any],
        abstract_text: str,
        event_callback: Optional[Callable[[str, str, str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Ask the patent writer Agent to repair an incomplete draft.

        Subjective drafting is intentionally kept inside the Hermes Agent LLM. The
        workflow engine may pass existing content and missing sections, but must not
        synthesize patent text or directly call writer tools outside the Agent loop.
        """
        if event_callback:
            event_callback(
                "CEO Agent",
                "agent.thinking",
                "🛠️ 撰写内容未补齐，继续调度专利撰写 Agent 补全必要章节",
                {"agent_name": "CEO Agent", "thought": "repair_incomplete_patent_draft"},
            )
        missing_items = []
        if not str((claims_data or {}).get("independent_claim") or "").strip():
            missing_items.append("权利要求书")
        for field_name, label in (
            ("technical_field", "技术领域"),
            ("background_art", "背景技术"),
            ("summary_of_invention", "发明内容"),
            ("detailed_description", "具体实施方式"),
        ):
            if not str((description_data or {}).get(field_name) or "").strip():
                missing_items.append(label)
        if not str(abstract_text or "").strip():
            missing_items.append("说明书摘要")
        requirement_output = self._latest_phase_output(
            context, WorkflowPhase.REQUIREMENT, "requirement_analysis"
        )
        retrieval_output = self._latest_phase_output(
            context, WorkflowPhase.RETRIEVAL, "retrieval_report"
        )
        confirmed_writer_context = self._build_confirmed_writer_context(
            context,
            requirement_output=requirement_output,
            retrieval_output=retrieval_output,
            limit=18000,
        )

        repair_prompt = f"""上一轮专利撰写输出不完整，请作为专利撰写 Agent 继续补齐，不要从头重写。

【已确认撰写上下文】
{confirmed_writer_context}

【需求分析】
{json.dumps(requirement_output or {}, ensure_ascii=False)[:3000]}

【检索报告】
{self._build_retrieval_summary_for_writer(retrieval_output, limit=12000)}

【已完成权利要求】
{json.dumps(claims_data or {}, ensure_ascii=False)[:6000]}

【已完成说明书】
{json.dumps(description_data or {}, ensure_ascii=False)[:8000]}

【已完成摘要】
{abstract_text or ""}

【待补齐内容】
{chr(10).join(f"- {item}" for item in missing_items) or "- 复核全部内容完整性"}

请按需调用 Hermes 工具获取结构、约束或支持性信号，但正式专利正文必须由你通过 LLM 生成。
最终只输出严格 JSON，格式为：
{{
  "claims": {{"independent_claim": "...", "dependent_claims": ["..."]}},
  "description": {{
    "technical_field": "...",
    "background_art": "...",
    "summary_of_invention": "...",
    "description_of_drawings": "...",
    "detailed_description": "..."
  }},
  "abstract": "...",
  "drawings": []
}}"""
        raw = await _run_agent_conversation_with_timeout(
            "patent.writer.v1",
            repair_prompt,
            timeout_seconds=_configured_timeout_seconds(
                "writer_revision_timeout_seconds",
                WRITER_REVISION_TIMEOUT_SECONDS,
            ),
        )
        if isinstance(raw, dict):
            text = raw.get("final_response", "") or raw.get("content", "") or json.dumps(raw, ensure_ascii=False)
            structured = raw.get("structured_result") if isinstance(raw.get("structured_result"), dict) else None
        else:
            text = str(raw or "")
            structured = None
        parsed = structured or self._try_parse_json(text)
        if not isinstance(parsed, dict) or "raw_output" in parsed:
            parsed = {
                "_agent_failed": True,
                "_incomplete_output": True,
                "_agent_error": "专利撰写 Agent 补齐结果不是有效 JSON，不能由本地文本解析替代。",
                "claims": {},
                "description": {},
                "abstract": "",
            }

        repaired_claims = dict(claims_data or {})
        parsed_claims = parsed.get("claims")
        if isinstance(parsed_claims, dict):
            normalized_claims = self._normalize_claims_payload(parsed_claims)
            if normalized_claims.get("independent_claim"):
                repaired_claims = normalized_claims

        repaired_description = dict(description_data or {})
        parsed_description = parsed.get("description")
        if isinstance(parsed_description, dict):
            for source_key, target_key in (
                ("technical_field", "technical_field"),
                ("background_art", "background_art"),
                ("summary_of_invention", "summary_of_invention"),
                ("description_of_drawings", "drawings_description"),
                ("drawings_description", "drawings_description"),
                ("detailed_description", "detailed_description"),
            ):
                value = parsed_description.get(source_key)
                if isinstance(value, str) and value.strip():
                    repaired_description[target_key] = value.strip()

        repaired_abstract = abstract_text or ""
        if isinstance(parsed.get("abstract"), str) and parsed["abstract"].strip():
            repaired_abstract = parsed["abstract"].strip()

        return {
            "claims": repaired_claims,
            "description": repaired_description,
            "abstract": repaired_abstract,
        }
    
    def _normalize_claims_payload(
        self,
        payload: Any,
        raw_response: Any = None,
    ) -> Dict[str, Any]:
        """Normalize claim_drafter output from structured tool data or wrapper JSON."""
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

        return {"independent_claim": "", "dependent_claims": []}

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
        return self._unwrap_agent_envelope(context_field="", data=context_data)

    def _unwrap_agent_envelope(self, context_field: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured JSON from Hermes Agent response envelopes.

        Hermes returns the Agent's natural final answer inside fields such as
        final_response/message/content. The workflow contract must validate that
        inner answer, while preserving tool traces for the UI. This is parsing
        only; it never invents missing phase fields.
        """
        if not isinstance(data, dict) or not data:
            return data
        if data.get("failed") is True or data.get("_agent_failed") is True:
            return data

        envelope_keys = ("final_response", "message", "content", "text", "output")
        for key in envelope_keys:
            raw_value = data.get(key)
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            parsed = self._try_parse_json(raw_value.strip())
            if not parsed or "raw_output" in parsed:
                continue
            normalized = dict(parsed)
            for preserve_key in (
                "tool_results",
                "_agent_tool_results",
                "events",
                "steps",
                "agent",
            ):
                if preserve_key in data and preserve_key not in normalized:
                    normalized[preserve_key] = data[preserve_key]
            normalized["_agent_envelope_normalized"] = True
            normalized["_raw_final_response"] = raw_value[:2000]
            if context_field:
                normalized["_context_field"] = context_field
            return normalized

        return data

    def _has_contract_value(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(self._has_contract_value(v) for v in value.values())
        if isinstance(value, list):
            return any(self._has_contract_value(v) for v in value)
        return bool(str(value or "").strip())

    def _validate_phase_contract(self, context_field: str, data: Any) -> List[str]:
        """Deterministic input/output contract gate for phase artifacts.

        This only checks structure and artifact presence. It must not decide
        patentability, creativity, claim scope, or writing quality.
        """
        if not isinstance(data, dict) or not data:
            return [f"{context_field} 未返回结构化对象"]
        if data.get("_agent_failed") is True:
            return [str(data.get("_agent_error") or f"{context_field} Agent 执行失败")]

        required_by_field = {
            "requirement_analysis": [
                "tech_field",
                "core_principle",
                "technical_problem",
                "beneficial_effects",
                "key_innovative_features",
                "application_scenarios",
                "patent_type_recommendation",
                "claim_skeleton",
            ],
            "retrieval_report": [
                "retrieval_strategy",
            ],
            "patent_draft": [
                "claims",
                "description",
                "abstract",
            ],
            "review_report": [
                "recommendation",
                "review_summary",
            ],
        }
        issues: List[str] = []
        for field_name in required_by_field.get(context_field, []):
            if not self._has_contract_value(data.get(field_name)):
                issues.append(f"{context_field} 缺少必需字段：{field_name}")

        if context_field == "retrieval_report":
            strategy = data.get("retrieval_strategy")
            keywords = data.get("retrieval_keywords")
            if isinstance(strategy, dict):
                keywords = strategy.get("keywords") or keywords
            if not self._has_contract_value(keywords):
                issues.append("retrieval_report 缺少实际检索关键词")

        if context_field == "patent_draft":
            claims = data.get("claims") if isinstance(data.get("claims"), dict) else {}
            if not self._has_contract_value(claims.get("independent_claim")):
                issues.append("patent_draft 缺少独立权利要求")
            if not self._has_contract_value(claims.get("dependent_claims")):
                issues.append("patent_draft 缺少从属权利要求")
            description = data.get("description") if isinstance(data.get("description"), dict) else {}
            for section in (
                "technical_field",
                "background_art",
                "summary_of_invention",
                "detailed_description",
            ):
                if not self._has_contract_value(description.get(section)):
                    issues.append(f"patent_draft 说明书缺少章节：{section}")
            for draft_issue in self._validate_patent_draft_completeness(data):
                if draft_issue in {
                    "patent_draft_agent_failed",
                    "patent_draft_incomplete_output",
                    "independent_claim_missing",
                    "dependent_claims_missing",
                    "claims_missing",
                    "description_missing",
                    "abstract_missing",
                }:
                    continue
                issues.append(f"patent_draft 硬规则不合格：{draft_issue}")
            working_docx_path = str(
                data.get("working_docx_path")
                or data.get("docx_draft_path")
                or data.get("draft_docx_path")
                or ""
            ).strip()
            if not working_docx_path:
                issues.append("patent_draft 缺少工作草稿 DOCX 路径：working_docx_path")

        if context_field == "review_report" and self._check_review_needs_revision(data):
            root_cause = str(data.get("root_cause") or "").strip()
            if root_cause not in {
                "content_incomplete",
                "requirement_unclear",
                "evidence_missing",
                "external_info_missing",
                "system_failure",
            }:
                issues.append("review_report 未通过时必须包含合法 root_cause")
            for issue in self._extract_review_issue_records(data):
                severity = str(issue.get("severity") or issue.get("likelihood") or "").lower()
                if severity not in {"high", "critical"}:
                    continue
                responsible_phase = str(
                    issue.get("responsible_phase")
                    or issue.get("target_phase")
                    or issue.get("route_to")
                    or ""
                ).strip()
                if responsible_phase not in {
                    "requirement_analysis",
                    "retrieval_analysis",
                    "patent_writing",
                    "user_input",
                    "system_failure",
                }:
                    issues.append("review_report high/critical 问题缺少合法 responsible_phase")
                    break

        return issues

    def _build_phase_contract_error(
        self,
        context_field: str,
        data: Any,
        issues: List[str],
    ) -> Dict[str, Any]:
        return {
            "_agent_failed": True,
            "_contract_failed": True,
            "_context_field": context_field,
            "_agent_error": "阶段输出不符合输入/输出契约：" + "；".join(issues[:8]),
            "_contract_issues": issues,
            "_raw_output": json.dumps(data, ensure_ascii=False, default=str)[:3000],
            "responsible_phase": context_field,
        }

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

        data = self._unwrap_agent_envelope(context_field, data)

        if context_field == "review_report" and (
            isinstance(data.get("final_response"), str)
            or isinstance(data.get("message"), str)
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
            return self._build_agent_output_error(
                context_field=context_field,
                output_text=json.dumps(data, ensure_ascii=False),
                reason=error_preview,
            )

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

        # ═══ 无法解析时只返回失败信息，不生成阶段内容 ═══
        if "raw_output" in data or ("agent" in data and "output" in data):
            output_text = raw_output_text or data.get("output", "") or data.get("raw_output", "")
            return self._build_agent_output_error(
                context_field=context_field,
                output_text=output_text,
                reason=f"{context_field} Agent 输出无法解析为当前要求的结构化数据",
            )

        if context_field == "patent_draft" and isinstance(data.get("tool_results"), list):
            normalized_from_tools = self._normalize_patent_draft_tool_results(data["tool_results"])
            if normalized_from_tools:
                normalized_from_tools["full_response"] = str(
                    data.get("final_response") or data.get("message") or data.get("text") or ""
                )
                return normalized_from_tools

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
                    data["similar_patents"] = refs  # 保留给既有前端字段读取

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

            # similar_patents → prior_art_references (front-end normalized format)
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

            # ===== 结构化字段归一化：兼容 Agent 输出中的等价字段名 =====

            # 1. 关键词字段: keywords_cn/keywords_en → retrieval_keywords
            if not data.get("retrieval_keywords"):
                keywords_fb = data.get("keywords_cn") or data.get("keywords_en") or data.get("query")
                if isinstance(keywords_fb, list):
                    data["retrieval_keywords"] = keywords_fb
                elif isinstance(keywords_fb, str) and keywords_fb.strip():
                    data["retrieval_keywords"] = [keywords_fb.strip()]

            # 2. 风险因素字段: risks → risk_factors
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

            # 3. 新颖性字段: novelty_score + novelty_rationale → novelty_assessment
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

            # 4. 创造性字段: inventive_step_score + inventive_step_rationale → inventive_step_assessment
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

            # 5. 实用性字段: utility_score + utility_rationale → utility_assessment
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

            # 6. 专利列表字段: similar_patents（字符串列表）→ prior_art_references
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
                                "relevance": "",
                                "abstract": "",
                                "differences": "",
                                "url": "",
                                "applicant": "",
                                "publication_date": "",
                            })
                    if refs:
                        data["prior_art_references"] = refs

            # 6b. 真实检索工具常见字段 → prior_art_references
            # 这里仅做结构归一，不生成或补造检索结论。
            if not data.get("prior_art_references"):
                candidate_items: List[Any] = []
                for key in (
                    "key_references",
                    "references",
                    "search_results",
                    "patent_results",
                    "retrieved_patents",
                    "citations",
                ):
                    value = data.get(key)
                    if isinstance(value, list):
                        candidate_items.extend(value)
                for nested_key in ("retrieval_results", "results"):
                    nested = data.get(nested_key)
                    if isinstance(nested, dict):
                        for key in ("references", "results", "patents"):
                            value = nested.get(key)
                            if isinstance(value, list):
                                candidate_items.extend(value)
                    elif isinstance(nested, list):
                        candidate_items.extend(nested)

                refs = []
                seen_ref_ids: set[str] = set()
                for item in candidate_items:
                    if isinstance(item, str):
                        patent_id = item.strip()
                        if not patent_id:
                            continue
                        source = ""
                        ref = {
                            "title": patent_id,
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": "",
                            "abstract": "",
                            "differences": "",
                            "url": self._build_patent_url(patent_id, source) if source else "",
                            "applicant": "",
                            "publication_date": "",
                        }
                    elif isinstance(item, dict):
                        patent_id = str(
                            item.get("reference_id")
                            or item.get("patent_id")
                            or item.get("patent_number")
                            or item.get("publication_number")
                            or item.get("document_id")
                            or ""
                        ).strip()
                        title = str(item.get("title") or item.get("name") or patent_id).strip()
                        if not patent_id and not title:
                            continue
                        source = str(item.get("source") or item.get("database") or "").strip()
                        score = item.get("similarity_score", item.get("score", 0))
                        risk = str(item.get("risk_level") or item.get("relevance") or "").strip()
                        if not risk:
                            if isinstance(score, (int, float)) and score >= 0.7:
                                risk = "high"
                            elif isinstance(score, (int, float)) and score >= 0.4:
                                risk = "medium"
                            else:
                                risk = ""
                        differences = (
                            item.get("key_differences")
                            or item.get("differences")
                            or item.get("distinguishing_features")
                            or ""
                        )
                        if isinstance(differences, list):
                            differences = "；".join(str(part) for part in differences if str(part).strip())
                        applicant = (
                            item.get("applicant")
                            or item.get("assignee")
                            or item.get("applicants")
                            or ""
                        )
                        if isinstance(applicant, list):
                            applicant = "、".join(str(part) for part in applicant if str(part).strip())
                        ref = {
                            "title": title,
                            "reference_id": patent_id,
                            "source": source,
                            "relevance": risk,
                            "abstract": item.get("abstract") or item.get("summary") or item.get("snippet") or "",
                            "differences": differences,
                            "url": item.get("url") or self._build_patent_url(patent_id, source),
                            "applicant": applicant,
                            "publication_date": item.get("publication_date") or item.get("publicationDate") or "",
                            **({"similarity_score": score} if isinstance(score, (int, float)) else {}),
                            "matching_features": item.get("matching_features") or item.get("key_features") or [],
                        }
                    else:
                        continue
                    dedupe_key = str(ref.get("reference_id") or ref.get("title") or "")
                    if dedupe_key in seen_ref_ids:
                        continue
                    seen_ref_ids.add(dedupe_key)
                    refs.append(ref)
                if refs:
                    data["prior_art_references"] = refs
                    data["similar_patents"] = refs

            # 7. 数据源字段: databases（顶层）→ retrieval_databases
            if "retrieval_databases" not in data:
                dbs = data.get("databases")
                if isinstance(dbs, list) and dbs:
                    data["retrieval_databases"] = dbs

            if "confirmed_sources" not in data:
                confirmed_sources: List[Dict[str, Any]] = []
                seen_sources: set[str] = set()

                def add_source(item: Any, default_type: str = "") -> None:
                    if isinstance(item, dict):
                        title = str(item.get("title") or item.get("name") or item.get("reference_id") or item.get("url") or "").strip()
                        url = str(item.get("url") or item.get("source_url") or "").strip()
                        source = str(item.get("source") or item.get("source_type") or item.get("database") or default_type).strip()
                        excerpt = str(
                            item.get("key_excerpt")
                            or item.get("abstract")
                            or item.get("summary")
                            or item.get("snippet")
                            or item.get("rationale")
                            or ""
                        ).strip()
                        why = str(item.get("why_it_matters") or item.get("differences") or item.get("relevance") or "").strip()
                    else:
                        title = str(item or "").strip()
                        url = ""
                        source = default_type
                        excerpt = ""
                        why = ""
                    if not (title or url):
                        return
                    key = f"{source}|{title}|{url}"
                    if key in seen_sources:
                        return
                    seen_sources.add(key)
                    confirmed_sources.append({
                        "title": title,
                        "url": url,
                        "source": source,
                        "key_excerpt": excerpt,
                        "why_it_matters": why,
                    })

                for field_name, default_type in (
                    ("prior_art_references", "patent"),
                    ("similar_patents", "patent"),
                    ("web_evidence", "web"),
                    ("non_patent_prior_art", "non_patent"),
                    ("evidence_sources", "evidence"),
                ):
                    for item in self._as_nonempty_list(data.get(field_name)):
                        add_source(item, default_type)

                for assessment_key in ("novelty_assessment", "inventive_step_assessment"):
                    assessment = data.get(assessment_key)
                    if not isinstance(assessment, dict):
                        continue
                    for item in self._as_nonempty_list(assessment.get("related_prior_art")):
                        add_source(item, "non_patent")

                if confirmed_sources:
                    data["confirmed_sources"] = confirmed_sources
            data.setdefault("evidence_gaps", [])

        elif context_field == "review_report":
            summary = data.get("review_summary")
            if isinstance(summary, dict):
                if "recommendation" not in data and summary.get("recommendation"):
                    data["recommendation"] = summary.get("recommendation")
                if "overall_score" not in data and summary.get("overall_score") is not None:
                    data["overall_score"] = summary.get("overall_score")
            # score → overall_score (如果 Agent 用了 score 字段)
            if "score" in data and "overall_score" not in data:
                data["overall_score"] = data["score"]
            target_agent_phase_map = {
                "patent_writer": "patent_writing",
                "writer": "patent_writing",
                "requirement_analyst": "requirement_analysis",
                "brainstorm_partner": "requirement_analysis",
                "retrieval_analyst": "retrieval_analysis",
                "quality_reviewer": "system_failure",
                "ceo": "system_failure",
            }
            for section_key in (
                "formal_compliance_review",
                "claims_review",
                "description_review",
                "consistency_review",
                "drawing_review",
                "drawings_review",
                "figure_review",
            ):
                section = data.get(section_key)
                if not isinstance(section, dict):
                    continue
                issues = section.get("issues")
                if not isinstance(issues, list):
                    continue
                for issue in issues:
                    if not isinstance(issue, dict) or issue.get("responsible_phase"):
                        continue
                    target_agent = str(issue.get("target_agent") or "").strip().lower()
                    responsible_phase = target_agent_phase_map.get(target_agent)
                    if responsible_phase:
                        issue["responsible_phase"] = responsible_phase
            for risk in data.get("examination_risks", []) or []:
                if not isinstance(risk, dict) or risk.get("responsible_phase"):
                    continue
                target_agent = str(risk.get("target_agent") or "").strip().lower()
                responsible_phase = target_agent_phase_map.get(target_agent)
                if not responsible_phase:
                    risk_text = " ".join(
                        str(risk.get(key) or "")
                        for key in (
                            "risk_type",
                            "description",
                            "mitigation_suggestion",
                            "mitigation",
                            "suggestion",
                        )
                    )
                    if any(token in risk_text for token in ("检索", "证据", "现有技术", "背景技术", "公开文献")):
                        responsible_phase = "retrieval_analysis"
                    elif any(token in risk_text for token in ("用户", "补充交底", "业务约束")):
                        responsible_phase = "user_input"
                    else:
                        responsible_phase = "patent_writing"
                if responsible_phase:
                    risk["responsible_phase"] = responsible_phase
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

    def _normalize_patent_draft_tool_results(
        self,
        tool_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build patent draft data from real Hermes tool results only."""
        claims_data: Dict[str, Any] = {}
        description_data: Dict[str, Any] = {}
        abstract_text = ""
        docx_path = ""
        drawings_data: List[Dict[str, Any]] = []

        for result in tool_results:
            if not isinstance(result, dict):
                continue
            tool_name = str(result.get("tool") or result.get("name") or "")
            payload = self._parse_tool_result_payload(
                result.get("result")
                or result.get("content")
                or result.get("output")
                or result
            )
            if not payload:
                continue
            if not tool_name:
                tool_name = str(payload.get("tool") or "")
            tool_data = payload.get("data", {})
            if not isinstance(tool_data, dict):
                tool_data = {}
            if payload.get("success") is False:
                continue

            if tool_name == "claim_drafter":
                candidate_claims = self._normalize_claims_payload(
                    tool_data,
                    raw_response=payload.get("raw_response"),
                )
                if candidate_claims.get("independent_claim"):
                    claims_data = candidate_claims
            elif tool_name == "description_writer":
                section_type = str(tool_data.get("section_type") or "")
                content = str(tool_data.get("content") or "").strip()
                if not content:
                    continue
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
            elif tool_name == "patent_drawing_generator":
                drawings = tool_data.get("drawings", [])
                if isinstance(drawings, list):
                    drawings_data.extend(item for item in drawings if isinstance(item, dict))
            elif tool_name == "patent_docx_generator":
                docx_path = str(tool_data.get("file_path") or docx_path)
                abstract_text = str(tool_data.get("abstract") or abstract_text)

        if not (claims_data or description_data or abstract_text or drawings_data or docx_path):
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
        }

    def _build_review_report_from_agent_envelope(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recover a structured quality review from the Agent final response only.

        Tool results are retained as trace data for the UI, but the workflow must not
        convert tool signals into a review conclusion. Subjective quality judgment
        belongs to the quality reviewer Agent LLM.
        """
        raw_text = str(data.get("final_response") or data.get("message") or "")
        parsed: Dict[str, Any] = {}
        if raw_text.strip():
            parsed_candidate = self._try_parse_json(raw_text)
            if parsed_candidate:
                parsed = parsed_candidate
            else:
                parsed = self._build_agent_output_error(
                    context_field="review_report",
                    output_text=raw_text,
                    reason="审查 Agent 最终回复无法解析为当前要求的结构化审查意见",
                )

        if not parsed:
            parsed = self._build_agent_output_error(
                context_field="review_report",
                output_text=raw_text,
                reason="审查 Agent 未返回当前要求的结构化审查意见",
            )

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
        if isinstance(tool_results, list) and tool_results:
            parsed["_agent_tool_results"] = tool_results

        parsed["_raw_final_response"] = raw_text[:2000] if raw_text else ""
        parsed["_agent_envelope_normalized"] = True
        return parsed

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

    def _build_agent_output_error(
        self,
        context_field: str,
        output_text: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Return explicit Agent failure metadata without synthesizing stage content."""
        error_msg = str(reason or "Agent 输出不符合当前结构化要求")[:500]
        raw_output = str(output_text or "")
        self._logger.warning(
            "Agent output rejected for %s: %s",
            context_field,
            error_msg[:200],
        )
        return {
            "_agent_failed": True,
            "_incomplete_output": True,
            "_context_field": context_field,
            "_agent_error": error_msg,
            "_raw_output": raw_output[:3000],
        }

    def _build_patent_url(self, patent_id: str, source: str) -> str:
        """根据专利号和来源构造可点击跳转的 URL"""
        if not patent_id:
            return ""

        source_lower = source.lower() if source else ""
        pid = patent_id.strip()

        if source_lower in ("uspto", "美国专利商标局"):
            clean_id = pid.replace("/", "").replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("google_patents", "google patents"):
            clean_id = pid.replace(" ", "")
            return f"https://patents.google.com/patent/{clean_id}"
        elif source_lower in ("arxiv", "arxiv 学术论文"):
            return f"https://arxiv.org/abs/{pid}"
        return ""

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
        timeout_seconds: int = 900,
    ) -> tuple[str, Dict[str, Any]]:
        """Run the quality reviewer with a bounded wait.

        Quality review is a required gate. If the reviewer LLM/tool chain hangs,
        return a structured non-approval result so the CEO remediation loop can
        retry or stop for human attention. Local heuristics must not approve.
        """
        label = f"（{round_label}）" if round_label else ""
        try:
            agent_result = await asyncio.wait_for(
                self._run_agent_stream(
                    service,
                    profile_id,
                    review_prompt,
                    context,
                    "质量审查 Agent",
                    event_callback=event_callback,
                ),
                timeout=timeout_seconds,
            )
            agent_text = str(agent_result.get("text") or "")
            context_data = self._build_context_data_from_agent_response(
                "quality_reviewer",
                agent_text,
                agent_result.get("tool_results", []),
                agent_result.get("structured_result"),
            )
            context_data = self._normalize_phase_output("review_report", context_data)
            context_data = self._merge_manual_compliance_into_review(context, context_data)
            return agent_text[:500], context_data
        except asyncio.TimeoutError:
            reason = f"质量审查 Agent{label}超过 {timeout_seconds}s 未完成"
        except Exception as exc:
            reason = f"质量审查 Agent{label}执行异常：{str(exc)[:180]}"

        self._logger.warning(
            f"{reason}; quality review marked as not approved",
            task_id=context.task_id,
        )
        if event_callback:
            event_callback(
                "质量审查 Agent",
                "agent.thinking",
                f"⚠️ {reason}，质量审查未通过，等待 CEO 重新调度",
                {
                    "agent_name": "质量审查 Agent",
                    "thought": "quality_review_unavailable",
                    "timeout_seconds": timeout_seconds,
                },
            )

        review = self._build_agent_output_error(
            context_field="review_report",
            output_text="",
            reason=reason,
        )
        review.update({
            "failed": True,
            "completed": False,
        })
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
            try:
                from src.core.config import settings

                configured_timeout = int(getattr(settings.workflow, "agent_timeout", 600) or 600)
            except Exception:
                configured_timeout = 600
            AGENT_TIMEOUT_SECONDS = max(60, configured_timeout)
            deadline = asyncio.get_event_loop().time() + AGENT_TIMEOUT_SECONDS
            while not result_holder["done"] or events:
                if asyncio.get_event_loop().time() > deadline:
                    self._logger.warning(
                        f"Agent {agent_name} timed out after {AGENT_TIMEOUT_SECONDS}s"
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
                    structured_result = {
                        "failed": True,
                        "completed": False,
                        "error": result_holder["error"],
                    }
                    final_text = ""
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
                "Agent stream failed",
                agent=agent_name,
                error=str(e),
                exc_info=True,
            )
            structured_result = {
                "failed": True,
                "completed": False,
                "error": str(e)[:500],
            }
            final_text = ""

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
