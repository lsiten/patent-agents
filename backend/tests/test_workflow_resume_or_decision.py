from __future__ import annotations

from src.api import routes
from src.core.workflow_engine import WorkflowContext


def _register_context(task_id: str, phase: str) -> WorkflowContext:
    context = WorkflowContext(task_id=task_id, user_id="test-user")
    context.current_phase = phase
    context.metadata["quality_remediation"] = {
        "current_score": 0.62,
        "threshold": 0.8,
        "classification": "needs_user_input",
        "missing_information": ["核心实施例的参数范围"],
        "attempt_count": 2,
        "recommended_next_action": "provide_info",
        "resume_phase": "requirement_analysis",
    }
    routes.workflow_engine._running_workflows[task_id] = context
    return context


def test_awaiting_user_decision_accepts_continue_auto_fix(client, api_prefix):
    task_id = "awaiting-continue"
    _register_context(task_id, "awaiting_user_decision")

    try:
        response = client.post(
            f"{api_prefix}/workflows/{task_id}/decision",
            json={"action": "continue_auto_fix"},
        )
        assert response.status_code == 200
    finally:
        routes.workflow_engine._running_workflows.pop(task_id, None)


def test_awaiting_user_decision_accepts_provide_info(client, api_prefix):
    task_id = "awaiting-provide"
    _register_context(task_id, "awaiting_user_decision")

    try:
        response = client.post(
            f"{api_prefix}/workflows/{task_id}/decision",
            json={
                "action": "provide_info",
                "supplemental_info": "补充了参数范围和部署约束",
            },
        )
        assert response.status_code == 200
    finally:
        routes.workflow_engine._running_workflows.pop(task_id, None)


def test_failed_workflow_is_not_resumable_through_decision_endpoint(client, api_prefix):
    task_id = "failed-decision"
    _register_context(task_id, "failed")

    try:
        response = client.post(
            f"{api_prefix}/workflows/{task_id}/decision",
            json={"action": "continue_auto_fix"},
        )
        assert response.status_code == 400
    finally:
        routes.workflow_engine._running_workflows.pop(task_id, None)
