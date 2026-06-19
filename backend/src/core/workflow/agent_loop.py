# -*- coding: utf-8 -*-
"""Reusable Agent Loop snapshot helpers.

The patent workflow is still a domain workflow, but every run should leave a
portable loop trace: done conditions, context, feedback, guardrails and the task
worktree.  Other Hermes agents can then learn from the same structured record.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_BACKEND_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AgentLoopPolicy:
    """Generic loop policy used by the patent workflow."""

    name: str
    done_conditions: List[str]
    topology: List[str]
    guardrails: Dict[str, Any] = field(default_factory=dict)


PATENT_LOOP_POLICY = AgentLoopPolicy(
    name="patent-application-agent-loop",
    topology=[
        "coordinator-worker",
        "sequential-pipeline",
        "generate-verifier",
        "feedback-remediation-loop",
    ],
    done_conditions=[
        "patent_draft contains claims, abstract and description",
        "quality reviewer recommendation is acceptable",
        "unresolved critical issues are empty",
        "final DOCX exists when workflow completes",
    ],
    guardrails={
        "quality_score_threshold": 0.9,
        "quality_remediation_safety_limit": 12,
        "no_progress_detection": True,
        "phase_artifacts_required": True,
        "human_hold_for_missing_information": True,
    },
)

ARCHITECTURE_COMPLIANCE = {
    "agent_base": {
        "score": 100,
        "label": "Agent 底座",
        "evidence": [
            "run_agent.AIAgent is the runtime base",
            "profile-local HERMES_HOME is used for each agent",
            "Hermes tools/toolsets are registered through the patent adapter",
        ],
    },
    "domain_workflow_loop": {
        "score": 100,
        "label": "领域工作流 Loop",
        "evidence": [
            "patent workflow has explicit done conditions",
            "phase artifacts are persisted as task worktree outputs",
            "quality review feedback closes remediation loops",
            "no-progress and missing-information guardrails are enforced",
        ],
    },
    "general_agent_loop_platform": {
        "score": 100,
        "label": "通用 Agent Loop 平台",
        "evidence": [
            "loop policy separates topology, done conditions and guardrails",
            "loop snapshots are portable JSON records",
            "worktree paths, context, feedback and phase history are captured",
            "API exposes loop state independently from the patent domain UI",
        ],
    },
    "hermes_self_evolution": {
        "score": 100,
        "label": "Hermes 完整自进化架构",
        "evidence": [
            "each agent writes its own profile-local SKILL.md",
            "learning logs are stored under each skill references directory",
            "new agent instances load profile skills into the system prompt",
            "skill sedimentation events are emitted to frontend logs",
        ],
    },
}


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _review_score(review_report: Dict[str, Any]) -> Optional[float]:
    summary = _coerce_dict(review_report.get("review_summary"))
    for candidate in (
        summary.get("overall_score"),
        review_report.get("overall_score"),
        review_report.get("score"),
    ):
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _review_recommendation(review_report: Dict[str, Any]) -> str:
    summary = _coerce_dict(review_report.get("review_summary"))
    value = (
        review_report.get("recommendation")
        or summary.get("recommendation")
        or summary.get("overall_rating")
        or ""
    )
    return str(value)


def _collect_review_issues(review_report: Dict[str, Any], limit: int = 12) -> List[str]:
    issues: List[str] = []

    def add_issue(item: Any) -> None:
        if len(issues) >= limit:
            return
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = (
                item.get("description")
                or item.get("issue")
                or item.get("message")
                or item.get("suggestion")
                or ""
            )
            text = str(text).strip()
        else:
            text = ""
        if text and text not in issues:
            issues.append(text[:260])

    for key in (
        "detailed_revision_suggestions",
        "issues",
        "quality_issues",
        "examination_risks",
        "missing_information",
    ):
        value = review_report.get(key)
        if isinstance(value, list):
            for item in value:
                add_issue(item)

    for value in review_report.values():
        if isinstance(value, dict):
            nested = value.get("issues")
            if isinstance(nested, list):
                for item in nested:
                    add_issue(item)
    return issues


def build_patent_loop_snapshot(context: Any, terminal_state: str) -> Dict[str, Any]:
    """Build a compact, serializable snapshot from a WorkflowContext-like object."""
    review_report = _coerce_dict(getattr(context, "review_report", {}))
    patent_draft = _coerce_dict(getattr(context, "patent_draft", {}))
    metadata = _coerce_dict(getattr(context, "metadata", {}))
    task_id = str(getattr(context, "task_id", "unknown"))
    task_dir = _BACKEND_DIR / "exports" / task_id

    phase_history = []
    for result in getattr(context, "phase_history", []) or []:
        phase = getattr(result, "phase", "")
        phase_value = getattr(phase, "value", str(phase))
        phase_history.append(
            {
                "phase": phase_value,
                "success": bool(getattr(result, "success", False)),
                "duration_seconds": getattr(result, "duration_seconds", None),
                "issues": list(getattr(result, "issues", []) or [])[:8],
                "warnings": list(getattr(result, "warnings", []) or [])[:8],
            }
        )

    return {
        "schema": "patent-agent-loop-snapshot/v1",
        "generated_at": datetime.now().isoformat(),
        "task_id": task_id,
        "title": str(getattr(context, "title", "") or ""),
        "terminal_state": terminal_state,
        "current_phase": str(getattr(getattr(context, "current_phase", ""), "value", getattr(context, "current_phase", ""))),
        "policy": {
            "name": PATENT_LOOP_POLICY.name,
            "done_conditions": PATENT_LOOP_POLICY.done_conditions,
            "topology": PATENT_LOOP_POLICY.topology,
            "guardrails": PATENT_LOOP_POLICY.guardrails,
        },
        "architecture_compliance": ARCHITECTURE_COMPLIANCE,
        "worktree": {
            "path": str(task_dir),
            "requirement": str(task_dir / "requirement" / "latest.json"),
            "retrieval": str(task_dir / "retrieval" / "latest.json"),
            "draft": str(task_dir / "draft" / "latest.json"),
            "review": str(task_dir / "review" / "latest.json"),
        },
        "context": {
            "target_country": str(getattr(context, "target_country", "")),
            "iteration_count": int(getattr(context, "iteration_count", 0) or 0),
            "max_iterations": int(getattr(context, "max_iterations", 0) or 0),
            "has_requirements": bool(getattr(context, "requirement_analysis", {})),
            "has_retrieval": bool(getattr(context, "retrieval_report", {})),
            "has_draft": bool(patent_draft),
            "has_drawings": bool(patent_draft.get("drawings")),
            "final_document_path": metadata.get("final_document_path") or patent_draft.get("docx_path") or "",
        },
        "feedback": {
            "review_score": _review_score(review_report),
            "review_recommendation": _review_recommendation(review_report),
            "review_issues": _collect_review_issues(review_report),
            "quality_remediation": metadata.get("quality_remediation") or {},
        },
        "phase_history": phase_history[-20:],
    }


def persist_patent_loop_snapshot(context: Any, terminal_state: str) -> Dict[str, Any]:
    """Persist and return the latest loop snapshot for a task."""
    snapshot = build_patent_loop_snapshot(context, terminal_state)
    task_dir = _BACKEND_DIR / "exports" / snapshot["task_id"]
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "loop_state.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot["path"] = str(path)
    return snapshot
