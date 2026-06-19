"""Official LangGraph runtime for patent workflows.

LangGraph owns workflow node identity, state snapshots, route history, and
interrupt recovery. Hermes remains the professional Agent execution substrate;
the engine method invoked from the graph runs the domain phase pipeline and
emits AG-UI events for every phase round, tool call, quality gate, and shared
fact update.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from langgraph.graph import END, START, StateGraph

from .nodes import GRAPH_NODE_SEQUENCE, TERMINAL_PIPELINE_STATES
from .state import PatentWorkflowState


class PatentWorkflowGraphRuntime:
    """LangGraph runtime that orchestrates the patent workflow state."""

    def __init__(self, engine: Any):
        self.engine = engine
        self.graph = self._build_graph()

    @property
    def node_names(self) -> tuple[str, ...]:
        return GRAPH_NODE_SEQUENCE

    def _build_graph(self):
        builder = StateGraph(PatentWorkflowState)
        for node in GRAPH_NODE_SEQUENCE:
            if node == "requirement_analysis":
                builder.add_node(node, self._run_domain_pipeline)
            else:
                builder.add_node(node, self._mark_node(node))

        builder.add_edge(START, "brainstorm")
        builder.add_edge("brainstorm", "title_generation")
        builder.add_edge("title_generation", "human_confirm_start")
        builder.add_edge("human_confirm_start", "requirement_analysis")
        builder.add_conditional_edges(
            "requirement_analysis",
            self._route_after_pipeline,
            {
                "end": END,
                "requirement_gate": "requirement_gate",
            },
        )
        builder.add_edge("requirement_gate", "retrieval")
        builder.add_edge("retrieval", "retrieval_gate")
        builder.add_edge("retrieval_gate", "writing")
        builder.add_edge("writing", "writing_gate")
        builder.add_edge("writing_gate", "quality_review")
        builder.add_edge("quality_review", "quality_gate")
        builder.add_edge("quality_gate", "final_docx")
        builder.add_edge("final_docx", END)
        return builder.compile()

    def _mark_node(self, node: str) -> Callable[[PatentWorkflowState], PatentWorkflowState]:
        async def _node(state: PatentWorkflowState) -> PatentWorkflowState:
            return self._with_route(state, node)

        return _node

    def _with_route(self, state: PatentWorkflowState, node: str) -> PatentWorkflowState:
        route_history = list(state.get("route_history") or [])
        route_history.append({"node": node, "timestamp": datetime.now().isoformat()})
        return {
            **state,
            "current_node": node,
            "route_history": route_history,
        }

    async def _run_domain_pipeline(self, state: PatentWorkflowState) -> PatentWorkflowState:
        state = self._with_route(state, "requirement_analysis")
        context = state["_context"]
        context.metadata["langgraph_runtime"] = {
            "enabled": True,
            "current_node": "requirement_analysis",
            "node_sequence": list(GRAPH_NODE_SEQUENCE),
        }
        context.metadata["_langgraph_runtime_active"] = True
        try:
            result_context = await self.engine._execute_langgraph_domain_pipeline(
                context,
                phase_callback=state.get("_phase_callback"),
                event_callback=state.get("_event_callback"),
                agent_event_callback=state.get("_agent_event_callback"),
                checkpoint_callback=state.get("_checkpoint_callback"),
                force_start_from=state.get("_force_start_from"),
            )
        finally:
            context.metadata.pop("_langgraph_runtime_active", None)

        return self._sync_from_context(state, result_context)

    def _route_after_pipeline(self, state: PatentWorkflowState) -> str:
        terminal_state = str(state.get("terminal_state") or "")
        if terminal_state in TERMINAL_PIPELINE_STATES:
            return "end"
        return "requirement_gate"

    def _sync_from_context(self, state: PatentWorkflowState, context: Any) -> PatentWorkflowState:
        current_phase = getattr(context.current_phase, "value", str(context.current_phase))
        metadata = getattr(context, "metadata", {}) or {}
        route_history = list(metadata.get("route_history") or state.get("route_history") or [])
        recorded_nodes = {str(item.get("node")) for item in route_history if isinstance(item, dict)}
        phase_to_node = {
            "brainstorming": "brainstorm",
            "brainstorm": "brainstorm",
            "requirement": "requirement_analysis",
            "requirement_analysis": "requirement_analysis",
            "retrieval": "retrieval",
            "retrieval_analysis": "retrieval",
            "writing": "writing",
            "patent_writing": "writing",
            "review": "quality_review",
            "quality_review": "quality_review",
        }
        for phase_result in getattr(context, "phase_history", []) or []:
            phase_value = getattr(getattr(phase_result, "phase", ""), "value", getattr(phase_result, "phase", ""))
            node = phase_to_node.get(str(phase_value))
            if not node or node in recorded_nodes:
                continue
            recorded_nodes.add(node)
            route_history.append(
                {
                    "node": node,
                    "phase": str(phase_value),
                    "timestamp": getattr(phase_result, "completed_at", None) or datetime.now().isoformat(),
                    "source": "phase_history",
                }
            )
        artifacts = {
            "requirement_analysis": getattr(context, "requirement_analysis", None),
            "retrieval_report": getattr(context, "retrieval_report", None),
            "patent_draft": getattr(context, "patent_draft", None),
            "review_report": getattr(context, "review_report", None),
            "final_document_path": getattr(context, "final_document_path", None)
            or metadata.get("final_document_path"),
        }
        return {
            **state,
            "_context": context,
            "current_node": self.engine._node_for_state(context.current_phase),
            "shared_facts": dict(getattr(context, "shared_agent_context", {}) or {}),
            "phase_rounds": dict(metadata.get("phase_rounds") or {}),
            "route_history": route_history,
            "interrupt": metadata.get("quality_remediation") or metadata.get("workflow_interrupt"),
            "artifacts": artifacts,
            "quality_score": float(getattr(context, "latest_review_score", 0.0) or 0.0),
            "terminal_state": current_phase,
        }

    async def run(
        self,
        context: Any,
        *,
        phase_callback: Optional[Callable[..., Any]] = None,
        event_callback: Optional[Callable[..., Any]] = None,
        agent_event_callback: Optional[Callable[..., Any]] = None,
        checkpoint_callback: Optional[Callable[..., Any]] = None,
        force_start_from: Any = None,
    ) -> Any:
        initial_state: PatentWorkflowState = {
            "task_id": context.task_id,
            "conversation_id": context.metadata.get("conversation_id"),
            "current_node": self.engine._node_for_state(context.current_phase),
            "shared_facts": dict(context.shared_agent_context or {}),
            "phase_rounds": dict(context.metadata.get("phase_rounds") or {}),
            "route_history": list(context.metadata.get("route_history") or []),
            "interrupt": context.metadata.get("quality_remediation")
            or context.metadata.get("workflow_interrupt"),
            "artifacts": {},
            "quality_score": float(getattr(context, "latest_review_score", 0.0) or 0.0),
            "terminal_state": getattr(context.current_phase, "value", str(context.current_phase)),
            "_context": context,
            "_phase_callback": phase_callback,
            "_event_callback": event_callback,
            "_agent_event_callback": agent_event_callback,
            "_checkpoint_callback": checkpoint_callback,
            "_force_start_from": force_start_from,
        }
        final_state = await self.graph.ainvoke(initial_state)
        return final_state.get("_context", context)
