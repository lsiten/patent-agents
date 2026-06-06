from __future__ import annotations

from src.core.events import EventType, InMemoryEventBus, RedisEventBus, WorkflowLogEvent


def test_workflow_log_event_serializes_unified_ulw_contract() -> None:
    event = WorkflowLogEvent(
        task_id="task-123",
        user_id="user-456",
        workflow="ulw",
        phase="green",
        status="success",
        summary="Focused test passed",
        detail="pytest backend/tests/test_workflow_log_event.py succeeded",
        trace_id="trace-789",
        parent_id="parent-001",
        artifacts=[{"label": "pytest", "path": "backend/tests/test_workflow_log_event.py"}],
        next_actions=["Run full backend tests"],
    )

    payload = event.to_dict()

    assert payload["event_type"] == "workflow.log"
    assert payload["task_id"] == "task-123"
    assert payload["user_id"] == "user-456"
    assert payload["workflow"] == "ulw"
    assert payload["phase"] == "green"
    assert payload["status"] == "success"
    assert payload["summary"] == "Focused test passed"
    assert payload["detail"] == "pytest backend/tests/test_workflow_log_event.py succeeded"
    assert payload["trace_id"] == "trace-789"
    assert payload["parent_id"] == "parent-001"
    assert payload["artifacts"] == [
        {"label": "pytest", "path": "backend/tests/test_workflow_log_event.py"}
    ]
    assert payload["next_actions"] == ["Run full backend tests"]


def test_workflow_log_event_defaults_keep_payload_stable() -> None:
    event = WorkflowLogEvent(
        task_id="task-123",
        user_id="user-456",
        phase="context",
        status="started",
        summary="Reading existing event model",
    )

    payload = event.to_dict()

    assert payload["workflow"] == "ulw"
    assert payload["detail"] is None
    assert payload["trace_id"] == "task-123"
    assert payload["parent_id"] is None
    assert payload["artifacts"] == []
    assert payload["next_actions"] == []


def test_workflow_log_event_is_streamed_by_in_memory_event_bus() -> None:
    bus = InMemoryEventBus()

    assert EventType.WORKFLOW_LOG in bus._sse_events


def test_workflow_log_event_reconstructs_from_redis_payload() -> None:
    bus = RedisEventBus(redis_client=None)
    original = WorkflowLogEvent(
        task_id="task-redis",
        user_id="user-456",
        phase="review",
        status="success",
        summary="reviewer gate passed",
    )

    reconstructed = bus._create_event_from_data(EventType.WORKFLOW_LOG, original.to_dict())

    assert isinstance(reconstructed, WorkflowLogEvent)
    assert reconstructed.event_type == EventType.WORKFLOW_LOG
    assert reconstructed.task_id == "task-redis"
    assert reconstructed.trace_id == "task-redis"
    assert reconstructed.phase == "review"
    assert reconstructed.status == "success"
    assert reconstructed.summary == "reviewer gate passed"


def test_workflow_log_event_uses_existing_task_event_fallback() -> None:
    from src.api import routes

    task_id = "task-workflow-log-fallback"
    routes.task_events.pop(task_id, None)

    routes._on_agent_event(
        WorkflowLogEvent(
            task_id=task_id,
            user_id="user-456",
            phase="surface",
            status="success",
            summary="curl returned schema-matching SSE payload",
            trace_id="trace-789",
        )
    )

    stored = routes.task_events[task_id][0]

    assert stored.task_id == task_id
    assert stored.agent == "ulw"
    assert stored.event_type == "workflow.log"
    assert stored.message == "[surface] curl returned schema-matching SSE payload"
    assert stored.data is not None
    assert stored.data["trace_id"] == "trace-789"

    routes.task_events.pop(task_id, None)
