"""LangGraph node registry for patent workflows."""

from __future__ import annotations

GRAPH_NODE_SEQUENCE = (
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


TERMINAL_PIPELINE_STATES = {
    "completed",
    "failed",
    "cancelled",
    "awaiting_user_decision",
}
