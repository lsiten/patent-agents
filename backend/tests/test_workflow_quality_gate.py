"""
Quality Gate Iteration Tests

These tests cover the bug where:
1. (Bug #1) Quality review agent finds critical issues, but the workflow
   completes anyway instead of looping back to the writer agent.
2. (Bug #2) The patent writer agent's fallback (when it can't parse output)
   injects "待生成" (to-be-generated) placeholders into the final draft.

Both bugs share a root cause: agent failures are silently swallowed and the
fallback function generates synthetic "looks-OK" data that masks the failure.
"""
from __future__ import annotations

import pytest

from src.core.workflow_engine import PatentWorkflowEngine


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _review_with_critical_issue() -> dict:
    """A review report with one critical issue in formal compliance."""
    return {
        "review_summary": {
            "overall_score": 0.45,
            "overall_rating": "poor",
            "recommendation": "reject",
            "reviewer_notes": "Critical issues found.",
        },
        "formal_compliance_review": {
            "score": 0.4,
            "passed": False,
            "issues": [
                {
                    "severity": "critical",
                    "location": "权利要求书",
                    "description": "权利要求保护范围过宽",
                    "suggestion": "缩小保护范围",
                }
            ],
        },
        "claims_review": {"issues": []},
        "description_review": {"issues": []},
        "consistency_review": {"issues": []},
        "examination_risks": [],
        "detailed_revision_suggestions": [],
        "revision_priority": "critical",
    }


def _review_with_agent_failure() -> dict:
    """A review report that is actually an API failure response."""
    return {
        "final_response": None,
        "messages": [{"role": "user", "content": "..."}],
        "api_calls": 1,
        "completed": False,
        "failed": True,
        "error": "Error code: 403 - Gemini API not enabled",
    }


def _clean_review() -> dict:
    """A review report with no issues — workflow should complete normally."""
    return {
        "review_summary": {
            "overall_score": 0.92,
            "overall_rating": "excellent",
            "recommendation": "approve",
            "reviewer_notes": "All checks passed.",
        },
        "formal_compliance_review": {"score": 0.95, "passed": True, "issues": []},
        "claims_review": {"issues": []},
        "description_review": {"issues": []},
        "consistency_review": {"issues": []},
        "examination_risks": [],
        "detailed_revision_suggestions": [],
        "revision_priority": "low",
    }


# ── Bug #1: Review with critical issues should trigger iteration ──────────────


class TestQualityGateTriggersRevision:
    """Bug #1: When review finds critical issues, workflow MUST loop back to writer."""

    def test_review_with_critical_issue_triggers_revision(self):
        engine = PatentWorkflowEngine()
        report = _review_with_critical_issue()
        assert engine._check_review_needs_revision(report) is True, (
            "A review with severity=critical issue must trigger revision"
        )

    def test_review_with_high_severity_triggers_revision(self):
        engine = PatentWorkflowEngine()
        report = _review_with_critical_issue()
        report["formal_compliance_review"]["issues"][0]["severity"] = "high"
        assert engine._check_review_needs_revision(report) is True

    def test_review_with_critical_revision_priority_triggers_revision(self):
        engine = PatentWorkflowEngine()
        report = _review_with_critical_issue()
        # Remove the critical issue, but keep priority=critical
        report["formal_compliance_review"]["issues"] = []
        report["revision_priority"] = "critical"
        assert engine._check_review_needs_revision(report) is True

    def test_review_with_reject_recommendation_triggers_revision(self):
        engine = PatentWorkflowEngine()
        report = _review_with_critical_issue()
        report["formal_compliance_review"]["issues"] = []
        assert engine._check_review_needs_revision(report) is True

    def test_clean_review_does_not_trigger_revision(self):
        engine = PatentWorkflowEngine()
        report = _clean_review()
        assert engine._check_review_needs_revision(report) is False, (
            "A clean review should NOT trigger revision"
        )

    def test_agent_failure_response_triggers_revision(self):
        """
        BUG #1 (CORE): When the review agent itself fails (API 403 etc.),
        the response looks like {"failed": True, "error": "..."} and does NOT
        have a structured review report. The workflow MUST treat this as a
        critical failure requiring iteration, NOT silently proceed to COMPLETED.
        """
        engine = PatentWorkflowEngine()
        failed_response = _review_with_agent_failure()
        assert engine._check_review_needs_revision(failed_response) is True, (
            "Agent failure (failed=True) MUST be treated as critical and trigger revision. "
            "Currently the workflow silently skips the iteration loop and produces "
            "garbage outputs — this is the root cause of Bug #1."
        )


# ── Bug #2: Writer fallback must never inject "待生成" placeholders ───────────


class TestWriterFallbackNoPlaceholders:
    """Bug #2: When the writer agent's output can't be parsed, the fallback
    function must NOT inject '待生成' placeholders. It should mark the data
    as incomplete and let the iteration loop retry."""

    def test_fallback_patent_draft_marks_failure(self):
        engine = PatentWorkflowEngine()
        # Simulate writer output that is just a 403 error message
        error_text = "Error code: 403 - Gemini API has not been used in project"
        result = engine._build_fallback_patent_draft(error_text)

        # The fallback MUST mark this as a failed agent execution
        assert result.get("_agent_failed") is True, (
            "Fallback must mark the patent_draft as agent-failed so downstream "
            "logic knows to retry instead of generating a .docx with placeholders"
        )

    def test_fallback_patent_draft_has_no_dai_sheng_cheng_placeholder(self):
        """
        BUG #2 (CORE): The current _build_fallback_patent_draft returns literal
        "待生成" strings. The fix must ensure those strings never appear in the
        final patent_draft structure.
        """
        engine = PatentWorkflowEngine()
        error_text = "Error code: 403 - Gemini API has not been used in project"
        result = engine._build_fallback_patent_draft(error_text)
        result_str = str(result)
        assert "待生成" not in result_str, (
            f"Fallback patent_draft contains '待生成' placeholder. Result: {result_str[:500]}"
        )

    def test_fallback_patent_draft_does_not_inject_prompt_text_as_content(self):
        """
        The current fallback uses regex to extract content from the (huge)
        error/prompt text and ends up storing the prompt's own section_type
        labels (e.g. 'section_type=\"background\":') as the "content" of those
        sections. This is a bug.
        """
        engine = PatentWorkflowEngine()
        error_text = """
        section_type="technical_field": ...
        section_type="background": ...
        section_type="summary": ...
        section_type="detailed": ...
        """
        result = engine._build_fallback_patent_draft(error_text)
        desc = result.get("description", {})
        # None of the description sections should contain the literal prompt labels
        for section_name, content in desc.items():
            if isinstance(content, str):
                assert "section_type=" not in content, (
                    f"description.{section_name} contains raw prompt text: {content[:200]}"
                )

    def test_fallback_review_report_marks_failure(self):
        """When review agent output can't be parsed, fallback must also
        mark the report as failed so the iteration loop triggers."""
        engine = PatentWorkflowEngine()
        error_text = "Error code: 403 - some LLM error"
        result = engine._build_fallback_review_report(error_text)
        assert result.get("_agent_failed") is True
        # The synthetic fallback should NOT set recommendation="approve" or
        # revision_priority="low" (which would skip the iteration)
        assert result.get("recommendation") != "approve"
        assert result.get("revision_priority") not in ("low", "medium")

    def test_fallback_review_report_no_unknown_recommendation(self):
        """The current fallback sets recommendation='unknown' which falls through
        every check in _check_review_needs_revision. This must be fixed."""
        engine = PatentWorkflowEngine()
        error_text = "Error code: 500 - server error"
        result = engine._build_fallback_review_report(error_text)
        # An "unknown" recommendation causes the workflow to silently skip
        # the iteration loop. The fix must make the recommendation either
        # "reject" (triggers iteration) or include a critical issue.
        rec = result.get("recommendation", "")
        if rec != "reject":
            # Must at least have a critical issue
            issues = result.get("formal_compliance_review", {}).get("issues", [])
            assert any(i.get("severity") in ("critical", "high") for i in issues), (
                f"Fallback review_report has no critical issues and recommendation={rec!r}, "
                f"which would cause _check_review_needs_revision to return False"
            )


# ── Integration: normalized output preserves failure status ──────────────────


class TestNormalizePhaseOutput:
    """_normalize_phase_output must propagate agent failure status."""

    def test_review_report_agent_failure_propagates(self):
        engine = PatentWorkflowEngine()
        failed = _review_with_agent_failure()
        normalized = engine._normalize_phase_output("review_report", failed)
        assert normalized.get("_agent_failed") is True
        # After normalization, _check_review_needs_revision MUST return True
        assert engine._check_review_needs_revision(normalized) is True

    def test_patent_draft_agent_failure_propagates(self):
        engine = PatentWorkflowEngine()
        # Simulate the dict produced when agent.run_conversation fails
        failed = _review_with_agent_failure()  # same shape
        normalized = engine._normalize_phase_output("patent_draft", failed)
        assert normalized.get("_agent_failed") is True
        # The patent_draft MUST NOT contain "待生成"
        assert "待生成" not in str(normalized)


# ── Final gate: workflow must not COMPLETE with unresolved critical issues ────


class TestWorkflowCompletionGate:
    """When max iterations are exhausted but the final review still has
    critical issues, the workflow must end in FAILED state, not COMPLETED.
    This is the user-facing manifestation of Bug #1."""

    def _complete_draft(self) -> dict:
        return {
            "claims": {
                "independent_claim": "1. 一种基于AI的图像分类方法，包括：步骤A；步骤B。",
                "dependent_claims": ["2. 根据权利要求1所述的方法..."],
            },
            "description": {
                "technical_field": "人工智能",
                "background_art": "现有技术存在准确率低的问题。",
                "summary_of_invention": "本发明提供一种...",
                "drawings_description": "",
                "detailed_description": "下面结合实施例详细说明...",
            },
            "abstract": "本发明公开了一种基于AI的图像分类方法。",
            "docx_path": "",
        }

    def _context_with_draft(self, draft: dict):
        from src.core.workflow_engine import WorkflowContext

        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = draft
        ctx.review_report = _clean_review()
        return ctx

    def test_final_state_failed_when_agent_failed(self):
        """If patent_draft has _agent_failed=True, the workflow should never
        reach COMPLETED with a .docx generated from empty content."""
        from src.core.workflow_engine import WorkflowContext, WorkflowState
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = {
            "_agent_failed": True,
            "_agent_error": "API 403",
            "claims": {"independent_claim": "", "dependent_claims": []},
            "description": {
                "technical_field": "",
                "background_art": "",
                "summary_of_invention": "",
                "drawings_description": "",
                "detailed_description": "",
            },
            "abstract": "",
            "docx_path": "",
        }
        ctx.review_report = _review_with_agent_failure()
        # The contract: this draft has NO real content. A check function
        # should detect this and refuse to mark the workflow as complete.
        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(ctx) is True

    def test_partial_draft_no_dependent_claims_blocked(self):
        """A complete application needs dependent claims, not only claim 1."""
        draft = self._complete_draft()
        draft["claims"]["dependent_claims"] = []

        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(self._context_with_draft(draft)) is True

    @pytest.mark.parametrize(
        "section_name",
        ["technical_field", "background_art", "summary_of_invention", "detailed_description"],
    )
    def test_partial_draft_missing_core_description_section_blocked(self, section_name):
        """Every core specification section must be present before completion."""
        draft = self._complete_draft()
        draft["description"][section_name] = ""

        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(self._context_with_draft(draft)) is True

    def test_partial_draft_declares_drawings_but_has_no_drawing_artifacts_blocked(self):
        """If the draft says drawings are needed, metadata/artifacts must exist."""
        draft = self._complete_draft()
        draft["description"]["drawings_description"] = "图1为系统结构示意图。"
        draft["drawings"] = []

        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(self._context_with_draft(draft)) is True

    def test_complete_draft_with_declared_drawings_allows_complete(self):
        """Declared drawings are complete when at least one safe artifact URL is present."""
        draft = self._complete_draft()
        draft["description"]["drawings_description"] = "图1为系统结构示意图。"
        draft["drawings"] = [
            {
                "figure_number": "图1",
                "title": "系统结构示意图",
                "description": "图1为系统结构示意图。",
                "artifact_url": "/api/v1/workflows/test/artifacts/draft/drawings/fig1.png",
            }
        ]

        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(self._context_with_draft(draft)) is False

    def test_writer_succeeded_review_passed_allow_complete(self):
        """If writer produced real content AND review passed, gate should NOT block."""
        from src.core.workflow_engine import WorkflowContext
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = {
            "claims": {
                "independent_claim": "1. 一种基于AI的图像分类方法，包括：步骤A；步骤B。",
                "dependent_claims": ["2. 根据权利要求1所述的方法..."],
            },
            "description": {
                "technical_field": "人工智能",
                "background_art": "现有技术存在准确率低的问题。",
                "summary_of_invention": "本发明提供一种...",
                "drawings_description": "",
                "detailed_description": "下面结合实施例详细说明...",
            },
            "abstract": "本发明公开了一种基于AI的图像分类方法。",
            "docx_path": "",
        }
        ctx.review_report = _clean_review()
        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(ctx) is False

    def test_writer_succeeded_review_critical_issue_block_complete(self):
        """If writer produced content but review has critical issue, gate should block."""
        from src.core.workflow_engine import WorkflowContext
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = {
            "claims": {
                "independent_claim": "1. 一种方法...",
                "dependent_claims": [],
            },
            "description": {
                "technical_field": "AI",
                "background_art": "...",
                "summary_of_invention": "...",
                "drawings_description": "",
                "detailed_description": "...",
            },
            "abstract": "本发明...",
        }
        ctx.review_report = _review_with_critical_issue()
        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(ctx) is True

    def test_partial_draft_no_description_blocked(self):
        """If writer only generated claims but no description/abstract, gate should block."""
        from src.core.workflow_engine import WorkflowContext
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = {
            "claims": {"independent_claim": "1. 一种方法...", "dependent_claims": []},
            "description": {
                "technical_field": "",
                "background_art": "",
                "summary_of_invention": "",
                "drawings_description": "",
                "detailed_description": "",
            },
            "abstract": "",
        }
        ctx.review_report = _clean_review()
        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(ctx) is True

    def test_partial_draft_no_claims_blocked(self):
        """If writer only generated description but no claims, gate should block."""
        from src.core.workflow_engine import WorkflowContext
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = {
            "claims": {"independent_claim": "", "dependent_claims": []},
            "description": {
                "technical_field": "AI",
                "background_art": "...",
                "summary_of_invention": "...",
                "drawings_description": "",
                "detailed_description": "...",
            },
            "abstract": "本发明...",
        }
        ctx.review_report = _clean_review()
        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(ctx) is True


class TestIterationAfterWriterFailure:
    """Bug #1 fix verification: writer failure MUST trigger iteration loop."""

    def test_iteration_loop_will_run_after_writer_failure(self):
        """Simulate the workflow state after the first round of agents:
        - Writer failed (Gemini API 403)
        - Review agent output is also a failure (same API key)
        Expected: _check_review_needs_revision returns True so the iteration
        loop in execute_full_workflow will run."""
        engine = PatentWorkflowEngine()
        writer_failed_output = {
            "final_response": None,
            "messages": [],
            "api_calls": 1,
            "completed": False,
            "failed": True,
            "error": "Error code: 403 - Gemini API has not been used",
        }
        # Normalize the writer output as it would be after _normalize_phase_output
        normalized_writer = engine._normalize_phase_output("patent_draft", writer_failed_output)
        assert normalized_writer.get("_agent_failed") is True

        # Normalize the review output as it would be after _normalize_phase_output
        review_failed_output = {
            "final_response": None,
            "messages": [],
            "api_calls": 1,
            "completed": False,
            "failed": True,
            "error": "Error code: 403 - Gemini API has not been used",
        }
        normalized_review = engine._normalize_phase_output("review_report", review_failed_output)
        assert normalized_review.get("_agent_failed") is True

        # The iteration check must return True so the loop re-runs
        assert engine._check_review_needs_revision(normalized_review) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
