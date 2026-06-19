"""AG-UI event normalization for workflow SSE streams.

The project keeps its historical SSE event names for backward compatibility, but
each event must also carry an AG-UI compatible event type and stable identifiers.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any, Dict, Mapping, MutableMapping, Optional


class AgUiEventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    STATE_DELTA = "STATE_DELTA"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    TOOL_CALL_END = "TOOL_CALL_END"
    PHASE_ROUND_STARTED = "PHASE_ROUND_STARTED"
    PHASE_ROUND_COMPLETED = "PHASE_ROUND_COMPLETED"
    QUALITY_GATE_COMPLETED = "QUALITY_GATE_COMPLETED"
    SHARED_FACTS_UPDATED = "SHARED_FACTS_UPDATED"
    HUMAN_INPUT_REQUESTED = "HUMAN_INPUT_REQUESTED"
    RUN_FINISHED = "RUN_FINISHED"


EVENT_TYPE_MAP: Mapping[str, AgUiEventType] = {
    "agent.message.start": AgUiEventType.TEXT_MESSAGE_START,
    "agent.thinking": AgUiEventType.TEXT_MESSAGE_CONTENT,
    "agent.content": AgUiEventType.TEXT_MESSAGE_CONTENT,
    "agent.message.end": AgUiEventType.TEXT_MESSAGE_END,
    "agent.dispatch": AgUiEventType.STATE_DELTA,
    "agent.tool_call_start": AgUiEventType.TOOL_CALL_START,
    "agent.tool_call_delta": AgUiEventType.TOOL_CALL_ARGS,
    "agent.tool_call_result": AgUiEventType.TOOL_CALL_RESULT,
    "agent.tool_call_end": AgUiEventType.TOOL_CALL_END,
    "workflow.phase_round.started": AgUiEventType.PHASE_ROUND_STARTED,
    "workflow.phase_round.completed": AgUiEventType.PHASE_ROUND_COMPLETED,
    "workflow.quality_gate.completed": AgUiEventType.QUALITY_GATE_COMPLETED,
    "workflow.shared_facts.updated": AgUiEventType.SHARED_FACTS_UPDATED,
    "workflow.human_input.requested": AgUiEventType.HUMAN_INPUT_REQUESTED,
    "workflow.run.started": AgUiEventType.RUN_STARTED,
    "workflow.run.finished": AgUiEventType.RUN_FINISHED,
    "workflow.state.delta": AgUiEventType.STATE_DELTA,
}


REQUIRED_EVENT_TYPES = tuple(event.value for event in AgUiEventType)


def agui_type_for(event_type: str) -> str:
    return EVENT_TYPE_MAP.get(event_type, AgUiEventType.STATE_DELTA).value


def stable_call_id(
    *,
    run_id: str,
    node: str,
    agent_name: str,
    call_name: str,
    round_index: Any = "",
) -> str:
    raw = f"{run_id}:{node}:{agent_name}:{call_name}:{round_index}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ensure_agui_payload(
    *,
    payload: Optional[MutableMapping[str, Any]],
    event_type: str,
    run_id: str,
    agent_name: str,
    node: str,
    status: str,
    current_round: Any,
    shared_facts_version: int,
    message: str,
) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(payload or {})
    agui_type = agui_type_for(event_type)
    call_name = (
        data.get("tool_name")
        or data.get("name")
        or data.get("tool")
        or data.get("skill")
        or event_type
    )
    round_index = data.get("iteration_count") or data.get("round") or current_round or ""
    data.setdefault("agui_type", agui_type)
    data.setdefault("type", agui_type)
    data.setdefault("run_id", run_id)
    data.setdefault("message_id", f"{run_id}:{node}:{round_index}")
    data.setdefault("parent_message_id", f"{run_id}:{node}")
    data.setdefault(
        "tool_call_id",
        stable_call_id(
            run_id=run_id,
            node=node,
            agent_name=agent_name,
            call_name=str(call_name),
            round_index=round_index,
        ),
    )
    data.setdefault(
        "state_delta",
        {
            "status": status,
            "current_node": node,
            "current_round": current_round,
            "shared_facts_version": shared_facts_version,
        },
    )
    data.setdefault("display_message", message)
    data.setdefault("agent_name", agent_name)
    return data

