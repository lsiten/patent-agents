from __future__ import annotations

import pytest

from langgraph.graph import END, START, StateGraph

from src.core.agui_events import AgUiEventType, REQUIRED_EVENT_TYPES, ensure_agui_payload
from src.core.workflow_engine import PatentWorkflowEngine, PhaseResult, WorkflowPhase, WorkflowState
from src.core.workflow_graph import PatentWorkflowGraphRuntime, PatentWorkflowState
from src.core.workflow_graph.runtime import GRAPH_NODE_SEQUENCE


def test_official_langgraph_dependency_is_available():
    graph = StateGraph(PatentWorkflowState)
    graph.add_node("start", lambda state: state)
    graph.add_edge(START, "start")
    graph.add_edge("start", END)

    compiled = graph.compile()

    assert compiled is not None


def test_patent_workflow_runtime_declares_expected_nodes():
    engine = PatentWorkflowEngine()
    runtime = PatentWorkflowGraphRuntime(engine)

    assert runtime.node_names == GRAPH_NODE_SEQUENCE
    assert runtime.node_names == (
        "brainstorm",
        "title_generation",
        "human_confirm_start",
        "requirement_analysis",
        "requirement_gate",
        "retrieval",
        "retrieval_gate",
        "writing",
        "writing_gate",
        "quality_review",
        "quality_gate",
        "final_docx",
    )


@pytest.mark.asyncio
async def test_execute_full_workflow_uses_langgraph_runtime(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="langgraph-runtime-entry",
        user_id="test-user",
        description="一种可自动调节显示姿态并处理多显示面画面的系统。",
    )

    async def fake_run(self, runtime_context, **kwargs):
        runtime_context.metadata["langgraph_runtime_called"] = True
        runtime_context.current_phase = WorkflowState.COMPLETED
        return runtime_context

    monkeypatch.setattr(PatentWorkflowGraphRuntime, "run", fake_run)

    result = await engine.execute_full_workflow(context)

    assert result.metadata["langgraph_runtime_called"] is True
    assert result.current_phase == WorkflowState.COMPLETED


@pytest.mark.asyncio
async def test_langgraph_runtime_calls_domain_pipeline_only_from_internal_seam(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="langgraph-domain-seam",
        user_id="test-user",
        description="一种可自动调节显示姿态并处理多显示面画面的系统。",
    )

    async def fake_domain_pipeline(runtime_context, **kwargs):
        assert runtime_context.metadata["_langgraph_runtime_active"] is True
        runtime_context.current_phase = WorkflowState.COMPLETED
        runtime_context.shared_agent_context["confirmed_solution"] = {"ready": True}
        return runtime_context

    monkeypatch.setattr(engine, "_execute_langgraph_domain_pipeline", fake_domain_pipeline)

    result = await PatentWorkflowGraphRuntime(engine).run(context)

    assert result.current_phase == WorkflowState.COMPLETED
    assert "_langgraph_runtime_active" not in result.metadata
    assert result.shared_agent_context["confirmed_solution"]["ready"] is True


@pytest.mark.asyncio
async def test_langgraph_runtime_recovers_route_history_from_phase_history(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="langgraph-route-history",
        user_id="test-user",
        description="一种可自动调节显示姿态并处理多显示面画面的系统。",
    )

    async def fake_domain_pipeline(runtime_context, **kwargs):
        runtime_context.current_phase = WorkflowState.COMPLETED
        runtime_context.phase_history.extend(
            [
                PhaseResult(phase=WorkflowPhase.REQUIREMENT, success=True, duration_seconds=1.0),
                PhaseResult(phase=WorkflowPhase.RETRIEVAL, success=True, duration_seconds=1.0),
                PhaseResult(phase=WorkflowPhase.WRITING, success=True, duration_seconds=1.0),
                PhaseResult(phase=WorkflowPhase.REVIEW, success=True, duration_seconds=1.0),
            ]
        )
        return runtime_context

    monkeypatch.setattr(engine, "_execute_langgraph_domain_pipeline", fake_domain_pipeline)

    runtime = PatentWorkflowGraphRuntime(engine)
    state = await runtime.graph.ainvoke(
        {
            "task_id": context.task_id,
            "conversation_id": None,
            "current_node": "brainstorm",
            "shared_facts": {},
            "phase_rounds": {},
            "route_history": [],
            "interrupt": None,
            "artifacts": {},
            "quality_score": 0.0,
            "terminal_state": "initialized",
            "_context": context,
        }
    )

    nodes = [item["node"] for item in state["route_history"]]
    assert "requirement_analysis" in nodes
    assert "retrieval" in nodes
    assert "writing" in nodes
    assert "quality_review" in nodes


def test_agui_payload_contains_required_protocol_fields():
    payload = ensure_agui_payload(
        event_type="workflow.phase_round.completed",
        payload={
            "task_id": "task-1",
            "message": "需求分析第 1 轮完成",
            "state_delta": {"current_node": "requirement_analysis", "current_round": 1},
        },
        run_id="task-1",
        agent_name="需求分析 Agent",
        node="requirement_analysis",
        status="running",
        current_round=1,
        shared_facts_version=2,
        message="需求分析第 1 轮完成",
    )

    for field in [
        "agui_type",
        "run_id",
        "message_id",
        "tool_call_id",
        "parent_message_id",
        "state_delta",
    ]:
        assert field in payload

    assert payload["agui_type"] == AgUiEventType.PHASE_ROUND_COMPLETED.value
    assert payload["run_id"] == "task-1"
    assert payload["state_delta"]["current_node"] == "requirement_analysis"
    assert payload["state_delta"]["current_round"] == 1


def test_required_agui_events_are_declared():
    declared = {event.value for event in AgUiEventType}

    assert set(REQUIRED_EVENT_TYPES).issubset(declared)
