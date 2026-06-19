"""State contract for the official LangGraph patent workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class PatentWorkflowState(TypedDict, total=False):
    task_id: str
    conversation_id: Optional[str]
    current_node: str
    shared_facts: Dict[str, Any]
    phase_rounds: Dict[str, List[Dict[str, Any]]]
    route_history: List[Dict[str, Any]]
    interrupt: Optional[Dict[str, Any]]
    artifacts: Dict[str, Any]
    quality_score: float
    terminal_state: str
    _context: Any
    _phase_callback: Any
    _event_callback: Any
    _agent_event_callback: Any
    _checkpoint_callback: Any
    _force_start_from: Any

