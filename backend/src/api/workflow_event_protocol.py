# -*- coding: utf-8 -*-
"""Workflow event protocol helpers for chat/activity views."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict

from .schemas import AgentEventInfo


def build_agent_activity_event(
    *,
    event_type: str,
    agent_name: str,
    sequence: int,
    call_id: str,
    message: str,
    data: Dict[str, Any],
    event_id: str | None = None,
) -> Dict[str, Any]:
    event = AgentEventInfo(
        id=event_id or str(uuid.uuid4()),
        sequence=sequence,
        call_id=call_id,
        type=event_type,
        agent_name=agent_name,
        timestamp=datetime.now().isoformat(),
        message=message,
        data=data,
    )
    return event.model_dump(mode="json")


def agent_activity_from_workflow_event(event: Dict[str, Any]) -> Dict[str, Any] | None:
    """Convert workflow/agent engine events to chat activity-log entries."""
    raw_type = str(event.get("event_type") or "")
    agent_name = str(event.get("agent_name") or event.get("agent_id") or "workflow_engine")
    task_id = str(event.get("task_id") or "workflow")

    activity_type = ""
    message = str(event.get("message") or "")
    data: Dict[str, Any] = {}
    call_id = str(event.get("call_id") or task_id)

    if raw_type == "agent.tool_call_start":
        tool_name = str(event.get("tool_name") or (event.get("data") or {}).get("name") or "unknown")
        params = event.get("parameters") or (event.get("data") or {}).get("parameters") or {}
        activity_type = "tool_call_start"
        message = message or f"调用工具: {tool_name}"
        data = {"name": tool_name, "parameters": params}
        call_id = f"{task_id}:{agent_name}:{tool_name}"
    elif raw_type == "agent.tool_call_end":
        tool_name = str(event.get("tool_name") or (event.get("data") or {}).get("name") or "unknown")
        result = event.get("result") or (event.get("data") or {}).get("result") or ""
        success = event.get("success", (event.get("data") or {}).get("success", True))
        activity_type = "tool_call_end"
        message = message or f"工具完成: {tool_name}"
        data = {"name": tool_name, "result": str(result)[:1200], "success": bool(success)}
        call_id = f"{task_id}:{agent_name}:{tool_name}"
    elif raw_type == "agent.thinking":
        thought = str(event.get("thought") or message or "")
        activity_type = "thinking"
        message = message or thought
        data = {"message": thought}
    elif raw_type == "agent.content":
        content = str(event.get("content") or message or "")
        activity_type = "content"
        message = message or content
        data = {"message": content, "phase": event.get("phase")}
    elif raw_type == "agent.skill_sedimented":
        payload = event.get("data") if isinstance(event.get("data"), dict) else {}
        skill = str(event.get("skill") or payload.get("skill") or "")
        activity_type = "content"
        message = message or f"已沉淀技能：{skill}"
        data = {
            "message": message,
            "skill": skill,
            "skill_path": event.get("skill_path") or payload.get("skill_path"),
            "log_path": event.get("log_path") or payload.get("log_path"),
        }
    elif raw_type.startswith("workflow."):
        activity_type = "status"
        message = message or raw_type
        data = {"kind": raw_type, "message": message}
    else:
        return None

    return build_agent_activity_event(
        event_type=activity_type,
        agent_name=agent_name,
        sequence=int(time.time() * 1000) % 1_000_000_000,
        call_id=call_id,
        message=message,
        data=data,
    )
