# -*- coding: utf-8 -*-
"""Input/output contracts for patent workflow phases."""

from __future__ import annotations

from typing import Any, Dict


PHASE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "requirement_analysis": {
        "node": "requirement_analysis",
        "inputs": [
            "user_disclosure",
            "brainstorm_output",
            "shared_facts",
            "retrieval_evidence",
            "previous_feedback",
        ],
        "required_outputs": [
            "tech_field",
            "technical_problem",
            "key_innovative_features",
            "information_gaps",
            "retrieval_feedback_review",
            "shared_facts_delta",
        ],
        "gate": "must_resolve_before_writing 为空或可由检索继续解决",
    },
    "retrieval_report": {
        "node": "retrieval",
        "inputs": [
            "requirement_gaps",
            "shared_facts",
            "previous_failed_queries",
        ],
        "required_outputs": [
            "retrieval_strategy",
            "retrieval_keywords",
            "sources_used",
            "retrieval_results",
            "resolved_questions",
            "unresolved_questions",
        ],
        "gate": "检索源不可用需记录并跳过；证据不足需调整检索式继续或明确转用户",
    },
    "patent_draft": {
        "node": "writing",
        "inputs": [
            "shared_facts",
            "requirement_analysis",
            "retrieval_report",
            "review_feedback",
            "writing_rules",
        ],
        "required_outputs": [
            "claims",
            "description",
            "abstract",
            "drawings",
            "docx_draft_path",
        ],
        "gate": "权利要求和说明书完整；附图由真实专利内容生成；DOCX 草稿可刷新",
    },
    "review_report": {
        "node": "quality_review",
        "inputs": [
            "patent_draft",
            "docx_draft",
            "drawings",
            "shared_facts",
            "manual_rules",
        ],
        "required_outputs": [
            "score",
            "recommendation",
            "issues",
            "root_cause",
            "route_to",
        ],
        "gate": "score >= 90 且无 high/critical 阻塞问题",
    },
}


def phase_contract_summary(context_field: str) -> Dict[str, Any]:
    """Return the contract used to instruct and validate a phase."""
    return PHASE_CONTRACTS.get(context_field, {"node": context_field})

