# -*- coding: utf-8 -*-
"""Domain models for the patent workflow runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class WorkflowState(str, Enum):
    """Workflow lifecycle states."""

    INITIALIZED = "initialized"
    BRAINSTORMING = "brainstorming"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    RETRIEVAL_ANALYSIS = "retrieval_analysis"
    PATENT_WRITING = "patent_writing"
    QUALITY_REVIEW = "quality_review"
    ITERATION = "iteration"
    AWAITING_USER_DECISION = "awaiting_user_decision"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowPhase(str, Enum):
    """Workflow phase identifiers used by persisted phase history."""

    BRAINSTORM = "brainstorm"
    REQUIREMENT = "requirement"
    RETRIEVAL = "retrieval"
    WRITING = "writing"
    REVIEW = "review"


@dataclass
class PhaseResult:
    """Result of a workflow phase or phase round."""

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
    """Mutable state shared across workflow phases."""

    def __init__(self, task_id: str, user_id: str, target_country: str = "中国"):
        self.task_id = task_id
        self.user_id = user_id
        self.target_country = target_country
        self.created_at = datetime.now()
        self.updated_at = self.created_at

        self.title: str = ""
        self.original_description: str = ""
        self.additional_materials: Dict[str, Any] = {}

        self.brainstorming_output: Dict[str, Any] = {}
        self.requirement_analysis: Dict[str, Any] = {}
        self.retrieval_report: Dict[str, Any] = {}
        self.patent_draft: Dict[str, Any] = {}
        self.review_report: Dict[str, Any] = {}

        self.iteration_count: int = 0
        self.max_iterations: int = 3
        self.current_phase: WorkflowState = WorkflowState.INITIALIZED
        self.phase_history: List[PhaseResult] = []
        self.metadata: Dict[str, Any] = {}
        self.shared_agent_context: Dict[str, Any] = {}
        self.is_paused: bool = False

        self.latest_revision_suggestions: List[str] = []
        self.latest_review_score: float = 0.0

        self.message_history: List[Dict[str, Any]] = []

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Append a chat/user message to workflow memory."""
        now = datetime.now()
        self.message_history.append(
            {
                "role": role,
                "content": content,
                "timestamp": now.isoformat(),
                **kwargs,
            }
        )
        if role == "user" and content:
            supplements = self.shared_agent_context.setdefault("user_supplements", [])
            if isinstance(supplements, list):
                supplements.append(
                    {
                        "content": content[:4000],
                        "timestamp": now.isoformat(),
                    }
                )
        self.updated_at = now

    def add_phase_result(self, result: PhaseResult) -> None:
        """Append a phase execution result."""
        self.phase_history.append(result)
        self.updated_at = datetime.now()

    def get_combined_input(self) -> str:
        """Return disclosure text plus confirmed shared context."""
        parts = [self.original_description]

        if self.metadata.get("patent_type_preference"):
            parts.append(f"\n\n用户偏好的专利类型: {self.metadata['patent_type_preference']}")

        shared_context_text = self.get_shared_agent_context_text()
        if shared_context_text:
            parts.append("\n\n已确认/共享公共信息:\n" + shared_context_text)

        if self.brainstorming_output and "summary" in self.brainstorming_output:
            parts.append("\n\n补充信息:\n" + self.brainstorming_output["summary"])

        key_messages = [
            message["content"]
            for message in self.message_history
            if message.get("role") in ["user", "assistant"] and len(message["content"]) > 50
        ]
        if key_messages:
            parts.append("\n\n讨论摘要:\n" + "\n".join(key_messages[-5:]))

        return "\n".join(parts)

    def get_shared_agent_context_text(self, limit: int = 10000) -> str:
        """Format confirmed facts and shared stage outputs for Agent prompts."""
        if not self.shared_agent_context:
            return ""
        return json.dumps(self.shared_agent_context, ensure_ascii=False, indent=2)[:limit]

    def merge_shared_agent_context(self, key: str, value: Any) -> None:
        """Merge a confirmed fact into shared workflow memory."""
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
            history.append(
                {
                    "version": new_version,
                    "key": key,
                    "timestamp": datetime.now().isoformat(),
                    "previous_preview": json.dumps(old_value, ensure_ascii=False, default=str)[
                        :1200
                    ]
                    if old_value not in (None, "", [], {})
                    else "",
                    "value_preview": json.dumps(value, ensure_ascii=False, default=str)[:2000],
                }
            )
            del history[:-100]
        self.metadata["shared_facts_version"] = new_version
        self.metadata["shared_agent_context"] = self.shared_agent_context
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the lightweight workflow status."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "current_state": self.current_phase.value,
            "iteration_count": self.iteration_count,
            "phase_count": len(self.phase_history),
            "phases_completed": [phase.phase.value for phase in self.phase_history],
        }
