# -*- coding: utf-8 -*-
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
import sys
import time
from datetime import datetime
from pathlib import Path as _Path
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
from src.core.workflow.protocol.agui_events import EVENT_TYPE_MAP, ensure_agui_payload
from src.core.workflow.artifacts import (
    get_phase_dir as _get_phase_dir,
    get_task_dir as _get_task_dir,
    persist_phase_result as _persist_phase_result,
    persist_workflow_checkpoint as _persist_workflow_checkpoint,
)
from src.core.workflow.phase_contracts import phase_contract_summary
from src.core.workflow.models import PhaseResult, WorkflowContext, WorkflowPhase, WorkflowState
from src.core.llm.client import LLMError
from src.core.constants.workflow import (
    AGENT_CONVERSATION_TIMEOUT_SECONDS,
    QUALITY_REMEDIATION_SAFETY_LIMIT,
    QUALITY_REMEDIATION_THRESHOLD,
    WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS,
    WRITER_INITIAL_TIMEOUT_SECONDS,
    WRITER_REVISION_TIMEOUT_SECONDS,
)
from src.core.patent.compliance import (
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

_AGUI_EVENT_MAP = {event_type: agui_type.value for event_type, agui_type in EVENT_TYPE_MAP.items()}


def _workflow_engine_override(name: str):
    """Return a monkeypatched helper from the public compatibility module.

    A number of tests and legacy callers patch ``src.core.workflow_engine``.
    The workflow is now split into mixins, so helpers imported into those
    modules need to resolve overrides dynamically instead of capturing the
    original function object forever.
    """
    current = globals().get(name)
    for module_name in ("src.core.workflow_engine", "src.core.workflow.engine"):
        module = sys.modules.get(module_name)
        candidate = getattr(module, name, None) if module is not None else None
        if candidate is not None and candidate is not current:
            return candidate
    return None


def _get_agent_factory_impl():
    """返回 Agent 配置注册表实例，用于工作流阶段调用 Agent。
    通过 create_ai_agent(profile_id) 创建 AIAgent，然后调用 agent.run_conversation(prompt)。
    """
    from src.agents.agent_config import get_agent_config_registry
    return get_agent_config_registry()


def _get_agent_factory():
    override = _workflow_engine_override("_get_agent_factory")
    if override is not None:
        return override()
    return _get_agent_factory_impl()


async def _run_agent_conversation_impl(
    profile_id: str,
    prompt: str,
    session_id: str | None = None,
    timeout_seconds: int = AGENT_CONVERSATION_TIMEOUT_SECONDS,
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


async def _run_agent_conversation(
    profile_id: str,
    prompt: str,
    session_id: str | None = None,
    timeout_seconds: int = AGENT_CONVERSATION_TIMEOUT_SECONDS,
) -> str | Dict[str, Any]:
    override = _workflow_engine_override("_run_agent_conversation")
    if override is not None:
        try:
            return await override(
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
                    return await override(profile_id, prompt, session_id)
                except TypeError as nested_exc:
                    nested_message = str(nested_exc)
                    if "positional" not in nested_message and "arguments" not in nested_message:
                        raise
            return await override(profile_id, prompt)
    return await _run_agent_conversation_impl(
        profile_id,
        prompt,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
    )


async def _run_agent_conversation_with_timeout(
    profile_id: str,
    prompt: str,
    *,
    session_id: str | None = None,
    timeout_seconds: int = AGENT_CONVERSATION_TIMEOUT_SECONDS,
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

__all__ = [name for name in globals() if not name.startswith("__")]
