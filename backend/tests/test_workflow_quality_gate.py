"""
Quality Gate Iteration Tests

These tests cover the bug where:
1. (Bug #1) Quality review agent finds critical issues, but the workflow
   completes anyway instead of looping back to the writer agent.
2. (Bug #2) The patent writer agent's parse-error path
   injects "待生成" (to-be-generated) placeholders into the final draft.

Both bugs share a root cause: agent failures are silently swallowed and the
workflow generates synthetic "looks-OK" data that masks the failure.
"""
from __future__ import annotations

import pytest

from src.core.workflow_engine import PatentWorkflowEngine, PhaseResult, WorkflowContext, WorkflowPhase, WorkflowState


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


class TestRetrievalPromptContracts:
    def test_retrieval_phase_prompt_includes_web_access_guidance(self):
        engine = PatentWorkflowEngine()
        context = WorkflowContext(task_id="retrieval-web", user_id="u-web")
        context.original_description = "一种结合产品文档与专利证据的技术检索方案。"
        context.requirement_analysis = {
            "tech_field": "人工智能",
            "key_innovative_features": ["网页证据补强"],
        }

        prompt = engine._build_phase_prompt(context, WorkflowState.RETRIEVAL_ANALYSIS)

        assert "web_access_match_site" in prompt
        assert "web_access_find_url" in prompt
        assert "web_access_read_page" in prompt
        assert "web_access_browser" in prompt
        assert "web_evidence" in prompt
        assert "non_patent_prior_art" in prompt
        assert "evidence_sources" in prompt
        assert "evidence_gaps" in prompt


class TestRequirementRetrievalReviewContracts:
    def test_nonblocking_impact_on_writing_allows_drafting(self):
        engine = PatentWorkflowEngine()
        review = {
            "ready_for_writing": True,
            "all_requirement_gaps_closed": False,
            "remaining_requirement_gaps": [
                {
                    "gap": "申请人内部是否已有具体型号尚未确认。",
                    "impact_on_writing": "不阻止撰写。当前保护策略是不写死型号。",
                }
            ],
        }

        assert engine._requirement_review_allows_drafting(review) is True

    def test_ready_for_writing_carries_retrieval_risks_without_relooping(self):
        engine = PatentWorkflowEngine()
        context = WorkflowContext(task_id="prewrite-ready", user_id="u-prewrite")
        requirement = {
            "tech_field": "沉浸式显示控制",
            "core_principle": "根据屏幕姿态联动画面处理策略。",
            "technical_problem": "屏幕姿态变化后画面连续性下降。",
            "beneficial_effects": ["保持多显示面画面连续"],
            "key_innovative_features": ["姿态与画面处理策略联合映射"],
            "application_scenarios": ["沉浸式多屏显示空间"],
            "patent_type_recommendation": "发明专利",
            "claim_skeleton": {"step_count": 4, "steps": ["获取", "确定", "控制", "处理"]},
            "information_gaps": ["尚未获得可核验的中国或国际专利对比文件。"],
            "retrieval_feedback_review": {
                "ready_for_writing": True,
                "all_requirement_gaps_closed": False,
                "remaining_requirement_gaps": [
                    {
                        "owner": "retrieval_analysis",
                        "gap": "专利数据库证据仍可继续补强。",
                        "impact_on_writing": "不阻止撰写，作为撰写和质量审查风险继续流转。",
                    }
                ],
                "search_feedback_for_retrieval": [
                    "继续补强 Google Patents 或 CNIPA 证据，但不影响技术方案撰写。"
                ],
            },
        }
        retrieval = {
            "retrieval_strategy": {
                "keywords": ["movable display", "projection mapping", "image remapping"],
                "databases_used": ["arxiv", "Microsoft Research"],
                "unavailable_sources": ["google_patents"],
            },
            "web_evidence": [
                {
                    "title": "RoomAlive - Microsoft Research",
                    "url": "https://www.microsoft.com/en-us/research/project/roomalive/",
                    "source_type": "official research page",
                }
            ],
            "non_patent_prior_art": [
                {
                    "title": "IllumiRoom",
                    "url": "https://www.microsoft.com/en-us/research/project/illumiroom-peripheral-projected-illusions-for-interactive-experiences/",
                },
                {
                    "title": "Projection Mapping Technologies for AR",
                    "url": "http://arxiv.org/abs/1704.02897v1",
                },
            ],
            "evidence_sources": [
                {"source": "google_patents", "status": "unavailable"},
                {"source": "arxiv", "status": "used"},
                {"source": "Microsoft Research", "status": "used"},
            ],
            "tool_results": [
                {"success": True, "result": "google_patents 数据源未配置或未启用"},
                {"success": True, "result": "arXiv returned http://arxiv.org/abs/1704.02897v1"},
                {"success": True, "result": "Microsoft Research https://www.microsoft.com/"},
            ],
            "evidence_gaps": ["专利源未配置，未取得专利号。"],
        }

        context.requirement_analysis = requirement
        context.retrieval_report = retrieval
        context.phase_history = [
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement),
            PhaseResult(WorkflowPhase.RETRIEVAL, True, 1.0, retrieval),
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement),
        ]

        assert engine._collect_prewriting_blockers(context) == []

    def test_repeated_source_limitations_are_carried_after_requirement_review(self):
        engine = PatentWorkflowEngine()
        context = WorkflowContext(task_id="prewrite-source-limit", user_id="u-source-limit")
        requirement_round_1 = {
            "tech_field": "沉浸式显示控制",
            "core_principle": "根据可动显示面姿态调整显示内容。",
            "technical_problem": "屏幕姿态变化后相邻画面衔接不连续。",
            "beneficial_effects": ["提高多显示面连续性"],
            "key_innovative_features": ["姿态变化与画面补偿策略联合控制"],
            "application_scenarios": ["沉浸式多屏显示空间"],
            "patent_type_recommendation": "发明专利",
            "claim_skeleton": {"step_count": 4, "steps": ["获取", "确定", "驱动", "生成"]},
            "information_gaps": ["继续补强 Google Patents 或 CNIPA 直接对比文件。"],
        }
        retrieval = {
            "retrieval_strategy": {
                "keywords": ["movable display", "projection mapping", "image compensation"],
                "databases_used": ["google_patents", "arxiv", "official_research_page"],
                "unavailable_sources": ["web_access_read_page: 浏览器远程调试未连接"],
            },
            "web_evidence": [
                {
                    "title": "Projection mapping research overview",
                    "url": "https://example.org/projection-mapping",
                }
            ],
            "non_patent_prior_art": [
                {
                    "title": "Dynamic projection mapping",
                    "url": "https://arxiv.org/abs/1234.5678",
                }
            ],
            "evidence_sources": [
                {"source": "Google Patents", "status": "无直接命中"},
                {"source": "arxiv", "status": "used"},
                {"source": "web_access_read_page", "status": "网页正文读取失败：远程调试不可用"},
            ],
            "tool_results": [
                {"success": True, "result": "Google Patents 未取得直接对比文件"},
                {"success": True, "result": "arXiv https://arxiv.org/abs/1234.5678"},
                {"success": True, "result": "web_access_read_page 网页正文读取失败：远程调试不可用"},
            ],
            "evidence_gaps": [
                "网页正文读取失败，远程调试不可用；Google Patents/CNIPA 未取得直接对比文件。"
            ],
        }
        requirement_round_2 = dict(requirement_round_1)
        requirement_round_2.update(
            {
                "information_gaps": [],
                "retrieval_feedback_review": {
                    "ready_for_writing": True,
                    "all_requirement_gaps_closed": False,
                    "remaining_requirement_gaps": [
                        {
                            "gap": "Google Patents/CNIPA 未取得直接对比文件。",
                            "impact_on_writing": "作为撰写和质量审查风险，不阻止撰写。",
                        }
                    ],
                    "search_feedback_for_retrieval": [
                        "网页正文读取失败，远程调试不可用；不应通过自动扫描调试端口绕过。"
                    ],
                },
            }
        )

        context.requirement_analysis = requirement_round_2
        context.retrieval_report = retrieval
        context.phase_history = [
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement_round_1),
            PhaseResult(WorkflowPhase.RETRIEVAL, True, 1.0, retrieval),
            PhaseResult(WorkflowPhase.RETRIEVAL, True, 1.0, retrieval),
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement_round_2),
        ]

        assert engine._collect_prewriting_blockers(context) == []
        assert "retrieval_source_limitations" in context.metadata["prewriting_carried_risks"]

    def test_missing_technical_facts_still_block_writing(self):
        engine = PatentWorkflowEngine()
        context = WorkflowContext(task_id="prewrite-hard-gap", user_id="u-hard-gap")
        requirement = {
            "tech_field": "沉浸式显示控制",
            "core_principle": "根据可动显示面姿态调整显示内容。",
            "technical_problem": "屏幕姿态变化后相邻画面衔接不连续。",
            "beneficial_effects": ["提高多显示面连续性"],
            "key_innovative_features": ["姿态变化与画面补偿策略联合控制"],
            "application_scenarios": ["沉浸式多屏显示空间"],
            "patent_type_recommendation": "发明专利",
            "claim_skeleton": {"step_count": 4, "steps": ["获取", "确定", "驱动", "生成"]},
            "information_gaps": ["缺少目标显示姿态与补偿画面生成之间的技术映射关系。"],
        }
        retrieval = {
            "retrieval_strategy": {
                "keywords": ["movable display", "projection mapping", "image compensation"],
                "databases_used": ["arxiv", "official_research_page"],
            },
            "web_evidence": [{"title": "Projection mapping", "url": "https://example.org/a"}],
            "non_patent_prior_art": [{"title": "Dynamic projection", "url": "https://arxiv.org/abs/1"}],
            "evidence_sources": [{"source": "arxiv", "status": "used"}],
            "tool_results": [{"success": True, "result": "arxiv https://arxiv.org/abs/1"}],
            "evidence_gaps": [],
        }
        context.requirement_analysis = requirement
        context.retrieval_report = retrieval
        context.phase_history = [
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement),
            PhaseResult(WorkflowPhase.RETRIEVAL, True, 1.0, retrieval),
            PhaseResult(WorkflowPhase.REQUIREMENT, True, 1.0, requirement),
        ]

        blockers = engine._collect_prewriting_blockers(context)
        assert blockers
        assert any("映射关系" in item["message"] for item in blockers)


class TestLowScoreRemediationContracts:
    """Low-score remediation contract tests for the next workflow iteration."""

    def test_extract_normalized_review_score_accepts_zero_to_one(self):
        engine = PatentWorkflowEngine()
        review = {"review_summary": {"overall_score": 0.78}}
        assert engine._extract_normalized_review_score(review) == 0.78

    def test_extract_normalized_review_score_accepts_percent_input(self):
        engine = PatentWorkflowEngine()
        review = {"review_summary": {"overall_score": 78}}
        assert engine._extract_normalized_review_score(review) == 0.78

    def test_low_score_incomplete_content_routes_to_writer(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.45,
                "overall_rating": "poor",
                "recommendation": "revise",
            },
            "root_cause": "content_incomplete",
            "missing_information": [],
        }
        ctx = WorkflowContext(task_id="t1", user_id="u1")
        assert engine._classify_remediation_path(review, ctx) == "WRITE_MORE"

    def test_requirement_unclear_routes_to_analysis(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.61,
                "overall_rating": "needs_revision",
                "recommendation": "revise",
            },
            "root_cause": "requirement_unclear",
            "missing_information": [],
        }
        ctx = WorkflowContext(task_id="t-analysis", user_id="u-analysis")
        assert engine._classify_remediation_path(review, ctx) == "ANALYZE_MORE"

    def test_evidence_missing_routes_to_search(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.58,
                "overall_rating": "needs_revision",
                "recommendation": "revise",
            },
            "root_cause": "evidence_missing",
            "missing_information": [],
        }
        ctx = WorkflowContext(task_id="t-search", user_id="u-search")
        assert engine._classify_remediation_path(review, ctx) == "SEARCH_MORE"

    def test_missing_information_routes_to_auto_remediation(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.62,
                "overall_rating": "needs_revision",
                "recommendation": "revise",
            },
            "root_cause": "external_info_missing",
            "missing_information": ["核心实施例的参数范围"],
        }
        ctx = WorkflowContext(task_id="t2", user_id="u2")
        assert engine._classify_remediation_path(review, ctx) == "ANALYZE_MORE"

    def test_missing_evidence_routes_to_retrieval_before_user_hold(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.62,
                "overall_rating": "needs_revision",
                "recommendation": "revise",
            },
            "root_cause": "external_info_missing",
            "missing_information": ["缺少公开专利或网页证据来源，需要交叉核验"],
        }
        ctx = WorkflowContext(task_id="t-search-missing", user_id="u-search-missing")
        assert engine._classify_remediation_path(review, ctx) == "SEARCH_MORE"

    def test_system_failure_routes_to_terminal_failure(self):
        engine = PatentWorkflowEngine()
        review = {
            "review_summary": {
                "overall_score": 0.2,
                "overall_rating": "poor",
                "recommendation": "reject",
            },
            "root_cause": "system_failure",
            "missing_information": [],
        }
        ctx = WorkflowContext(task_id="t-fail", user_id="u-fail")
        assert engine._classify_remediation_path(review, ctx) == "TERMINAL_FAILURE"

    def test_no_progress_still_fails(self):
        engine = PatentWorkflowEngine()
        ctx = WorkflowContext(task_id="t3", user_id="u3")
        ctx.iteration_count = 2
        shared_error = "Error code: 403 - Gemini API not enabled"
        ctx.patent_draft = {"_agent_failed": True, "_agent_error": shared_error}
        ctx.review_report = {"_agent_failed": True, "_agent_error": shared_error}
        ctx.phase_history = [
            PhaseResult(
                phase=WorkflowPhase.WRITING,
                success=False,
                duration_seconds=0,
                output={"_agent_failed": True, "_agent_error": shared_error},
                issues=[shared_error],
            ),
            PhaseResult(
                phase=WorkflowPhase.REVIEW,
                success=False,
                duration_seconds=0,
                output={"_agent_failed": True, "_agent_error": shared_error},
                issues=[shared_error],
            ),
        ]
        assert engine._iteration_making_no_progress(ctx) is True

    def test_awaiting_user_decision_does_not_silent_pass_completion_gate(self):
        engine = PatentWorkflowEngine()
        ctx = WorkflowContext(task_id="t-await", user_id="u-await")
        ctx.current_phase = "awaiting_user_decision"
        ctx.patent_draft = self._complete_draft() if hasattr(self, "_complete_draft") else {
            "claims": {
                "independent_claim": "1. 一种方法，包括步骤A。",
                "dependent_claims": ["2. 根据权利要求1所述的方法..."],
            },
            "description": {
                "technical_field": "人工智能",
                "background_art": "背景技术。",
                "summary_of_invention": "发明内容。",
                "drawings_description": "",
                "detailed_description": "实施方式。",
            },
            "abstract": "摘要。",
        }
        ctx.review_report = {
            "review_summary": {
                "overall_score": 0.55,
                "overall_rating": "needs_revision",
                "recommendation": "revise",
            },
            "root_cause": "external_info_missing",
            "missing_information": ["关键参数范围"],
        }
        assert engine._has_unresolved_critical_issues(ctx) is True


# ── Bug #2: Writer parse errors must never inject "待生成" placeholders ────────


class TestWriterOutputErrorNoPlaceholders:
    """When the writer agent's output can't be parsed, the workflow must NOT
    inject placeholders. It should mark the data as incomplete and let the
    iteration loop retry."""

    def test_patent_draft_output_error_marks_failure(self):
        engine = PatentWorkflowEngine()
        error_text = "Error code: 403 - Gemini API has not been used in project"
        result = engine._build_agent_output_error("patent_draft", error_text, error_text)

        assert result.get("_agent_failed") is True, (
            "Output error must mark the patent_draft as agent-failed so downstream "
            "logic knows to retry instead of generating a .docx with placeholders"
        )

    def test_patent_draft_output_error_has_no_dai_sheng_cheng_placeholder(self):
        """
        Malformed writer output must never produce literal "待生成" strings in the
        final patent_draft structure.
        """
        engine = PatentWorkflowEngine()
        error_text = "Error code: 403 - Gemini API has not been used in project"
        result = engine._build_agent_output_error("patent_draft", error_text, error_text)
        result_str = str(result)
        assert "待生成" not in result_str, (
            f"Patent draft error output contains '待生成' placeholder. Result: {result_str[:500]}"
        )

    def test_patent_draft_output_error_does_not_inject_prompt_text_as_content(self):
        """
        Error/prompt text must not be parsed into patent sections.
        """
        engine = PatentWorkflowEngine()
        error_text = """
        section_type="technical_field": ...
        section_type="background": ...
        section_type="summary": ...
        section_type="detailed": ...
        """
        result = engine._build_agent_output_error("patent_draft", error_text, error_text)
        desc = result.get("description", {})
        for section_name, content in desc.items():
            if isinstance(content, str):
                assert "section_type=" not in content, (
                    f"description.{section_name} contains raw prompt text: {content[:200]}"
                )

    def test_review_report_output_error_marks_failure(self):
        """When review agent output can't be parsed, mark the report as failed."""
        engine = PatentWorkflowEngine()
        error_text = "Error code: 403 - some LLM error"
        result = engine._build_agent_output_error("review_report", error_text, error_text)
        assert result.get("_agent_failed") is True
        assert result.get("recommendation") != "approve"
        assert result.get("revision_priority") not in ("low", "medium")

    def test_review_report_output_error_triggers_revision(self):
        """Agent output errors must trigger the review iteration."""
        engine = PatentWorkflowEngine()
        error_text = "Error code: 500 - server error"
        result = engine._build_agent_output_error("review_report", error_text, error_text)
        assert engine._check_review_needs_revision(result) is True


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


    def test_try_parse_json_accepts_dict_without_split(self):
        engine = PatentWorkflowEngine()
        payload = {"failed": True, "error": "timeout", "completed": False}
        assert engine._try_parse_json(payload) == payload

    def test_agent_response_helper_prefers_structured_result(self):
        engine = PatentWorkflowEngine()
        structured = {"failed": True, "error": "timeout", "completed": False}
        context_data = engine._build_context_data_from_agent_response(
            "quality_reviewer",
            "",
            [],
            structured,
        )
        normalized = engine._normalize_phase_output("review_report", context_data)
        assert normalized.get("_agent_failed") is True
        assert normalized.get("_agent_error") == "timeout"


    @pytest.mark.asyncio
    async def test_run_agent_stream_create_error_marks_structured_failure(self, monkeypatch):
        engine = PatentWorkflowEngine()
        context = WorkflowContext(task_id="stream-dict", user_id="u-stream")

        def fake_create_ai_agent(profile_id, callbacks=None):
            raise RuntimeError("stream unavailable")

        monkeypatch.setattr(
            "src.agents.agent_config.create_ai_agent",
            fake_create_ai_agent,
        )

        result = await engine._run_agent_stream(
            None,
            "patent.quality_reviewer.v1",
            "review prompt",
            context,
            "质量审查 Agent",
        )

        assert isinstance(result["text"], str)
        assert result["structured_result"]["failed"] is True
        assert result["structured_result"]["completed"] is False
        assert "stream unavailable" in result["structured_result"]["error"]

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
            "title": "一种图像分类处理方法及系统",
            "claims": {
                "independent_claim": (
                    "1. 一种基于AI的图像分类方法，其特征在于，包括：\n"
                    "S1、获取待分类图像；\n"
                    "S2、提取图像特征；\n"
                    "S3、输出分类结果。\n"
                ),
                "dependent_claims": [
                    "2. 根据权利要求1所述的方法，其特征在于，所述图像特征包括纹理特征、边缘特征和颜色特征中的至少一种，其中纹理特征的提取采用Gabor滤波器组在多个尺度和方向上进行，边缘特征通过Canny算子检测获得。\n",
                    "3. 一种基于AI的图像分类系统，其特征在于，包括：\n"
                    "图像获取模块，用于获取待分类图像；\n"
                    "特征提取模块，用于提取所述待分类图像的图像特征；\n"
                    "分类输出模块，用于根据所述图像特征输出分类结果。\n",
                ],
            },
            "description": {
                "technical_field": "本发明涉及图像识别与人工智能分类处理技术领域。",
                "background_art": (
                    "目前，图像分类系统通常通过卷积神经网络或特征匹配模型对输入图像进行类别预测。\n"
                    "例如，中国专利公开号CN110163188A公开了一种图像分类方法，能够利用图像特征执行类别识别。\n"
                    "然而，现有技术在低纹理图像或类别边界相近的场景下容易出现分类准确率下降的问题。"
                ),
                "summary_of_invention": (
                    "本发明要解决的技术问题是提高低纹理或近似类别图像的分类稳定性。\n"
                    "为解决上述技术问题，本发明提供一种基于AI的图像分类方法及系统，包括获取待分类图像、提取图像特征以及输出分类结果，并由对应模块执行上述处理。\n"
                    "本发明的有益效果在于提高分类准确率并减少近似类别误判。"
                ),
                "drawings_description": "",
                "detailed_description": (
                    "以下结合实施例对本发明进行说明。\n"
                    "S1、获取待分类图像，并对所述待分类图像进行尺寸归一化处理。\n"
                    "S2、提取图像特征，所述图像特征包括纹理特征和边缘特征。\n"
                    "S3、根据所述图像特征输出分类结果。\n"
                    "可以理解的是，上述步骤可以由处理器执行。\n"
                    "需要说明的是，各步骤的数据处理顺序可以根据实际部署环境进行流水化执行。"
                ),
            },
            "abstract": "本发明公开一种图像分类处理方法及系统，涉及图像识别与人工智能分类处理技术领域。该方法获取待分类图像，提取图像特征并输出分类结果，系统由对应模块执行上述处理。由此提高低纹理或近似类别图像的分类稳定性。",
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

    def test_method_and_system_title_without_system_independent_claim_blocked(self):
        """A method-and-system title needs a corresponding system independent claim."""
        draft = self._complete_draft()
        draft["claims"]["dependent_claims"] = [
            "2. 根据权利要求1所述的方法，其特征在于，所述图像特征包括纹理特征。\n"
        ]

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
        draft["description"]["drawings_description"] = "图1为系统结构示意图。图2为方法流程示意图。图3为模块交互示意图。图4为数据处理流程示意图。"
        draft["drawings"] = [
            {
                "figure_number": f"图{index}",
                "title": title,
                "description": title,
                "artifact_url": f"/api/v1/workflows/test/artifacts/draft/drawings/fig{index}.png",
                "prompt_version": "patent_drawing_v3",
            }
            for index, title in enumerate(
                [
                    "系统结构示意图",
                    "方法流程示意图",
                    "模块交互示意图",
                    "数据处理流程示意图",
                ],
                start=1,
            )
        ]

        engine = PatentWorkflowEngine()
        assert engine._has_unresolved_critical_issues(self._context_with_draft(draft)) is False

    def test_writer_succeeded_review_passed_allow_complete(self):
        """If writer produced real content AND review passed, gate should NOT block."""
        from src.core.workflow_engine import WorkflowContext
        ctx = WorkflowContext(task_id="test", user_id="test")
        ctx.patent_draft = self._complete_draft()
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
