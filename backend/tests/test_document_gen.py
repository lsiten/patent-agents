"""
Tests for patent document generator (DOCX export).
"""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from src.document_gen.generator import generate_patent_docx
from src.models.domain import (
    Claim,
    DescriptionSection,
    FinalPatent,
    PatentDraft,
    PatentTask,
    PriorArtReference,
    RetrievalReport,
    ReviewReport,
    ReviewResult,
)
from src.models.enums import Rating, Severity, WorkflowState


# ── Test Data Helpers ────────────────────────────────────────────────────────


def _make_draft() -> PatentDraft:
    """Create a realistic PatentDraft for testing."""
    return PatentDraft(
        title="一种基于深度学习的端到端情感分析系统及方法",
        technical_field="本发明涉及人工智能技术领域，具体涉及一种基于深度学习的端到端情感分析方法及系统。",
        background_art=DescriptionSection(
            section_name="背景技术",
            content="随着互联网的快速发展，文本数据呈现爆炸式增长，情感分析技术在舆情监控、智能客服等领域具有重要应用价值。然而现有的情感分析方法往往需要大量人工特征工程，泛化能力有限。",
        ),
        summary_of_invention=DescriptionSection(
            section_name="发明内容",
            content="本发明提供了一种基于深度学习的端到端情感分析方法及系统。本发明通过端到端的学习方式无需人工特征提取，能够自动从文本数据中学习情感特征。",
        ),
        description_of_drawings=DescriptionSection(
            section_name="附图说明",
            content="图1为本发明实施例提供的情感分析系统的结构示意图；图2为本发明实施例提供的情感分析方法的流程示意图。",
        ),
        detailed_description=DescriptionSection(
            section_name="具体实施方式",
            content="下面结合附图和具体实施例对本发明作进一步详细说明。实施例1：一种基于Transformer的情感分析模型包括输入层、编码层、分类层。",
        ),
        claims=[
            Claim(
                claim_number=1,
                claim_type="independent",
                content="一种基于深度学习的端到端情感分析方法，其特征在于包括以下步骤：步骤S1获取待分析的文本数据；步骤S2将所述文本数据输入训练好的情感分析模型得到情感分类结果。",
                category="方法",
            ),
            Claim(
                claim_number=2,
                claim_type="dependent",
                content="根据权利要求1所述的方法，其特征在于所述情感分析模型包括Transformer编码器和分类器。",
                dependencies=[1],
            ),
        ],
        abstract="本发明公开了一种基于深度学习的端到端情感分析系统及方法，能够自动从文本数据中学习情感特征。",
        key_terms_dictionary={
            "情感分析": "sentiment analysis, 对文本情感倾向进行分类分析的技术",
            "端到端": "end-to-end, 从原始输入直接到最终输出的学习范式",
        },
    )


def _make_retrieval_report() -> RetrievalReport:
    """Create a realistic RetrievalReport for test FinalPatent."""
    return RetrievalReport(
        novelty_assessment=Rating.HIGH,
        novelty_rationale="现有技术中未见公开本发明的端到端情感分析方案",
        inventive_step_assessment=Rating.MEDIUM,
        inventive_step_rationale="基于Transformer的情感分析虽已存在但本发明在模型结构上有改进",
        utility_assessment=Rating.HIGH,
        utility_rationale="具有明确的工业应用价值",
        overall_patentability=Rating.HIGH,
        overall_confidence=0.85,
        prior_art_found=[
            PriorArtReference(
                reference_id="CN202010123456",
                title="一种基于神经网络的情感分析方法",
                publication_date="2022-03-15",
                abstract="一种基于神经网络的情感分析方法",
                similarity_score=0.6,
                technical_differences=["本发明采用端到端学习方式"],
                source="cnipa",
            )
        ],
        writing_recommendations=["强调端到端学习的创新性"],
        claim_strategy_recommendations=["权利要求应突出技术效果"],
        risk_factors=["可能存在Transformer相关的基础专利风险"],
    )


def _make_review_report() -> ReviewReport:
    """Create a realistic ReviewReport for test FinalPatent."""
    return ReviewReport(
        formal_compliance=ReviewResult(passed=True, score=0.95),
        claims_review=ReviewResult(passed=True, score=0.88),
        description_review=ReviewResult(passed=True, score=0.92),
        consistency_review=ReviewResult(passed=True, score=0.90),
        prior_art_risk=ReviewResult(passed=True, score=0.85),
        overall_score=0.90,
        recommendation="approve",
        revision_priority=Severity.LOW,
        estimated_office_action_risk=0.3,
    )


def _make_final_patent(task_id: str) -> FinalPatent:
    """Helper: FinalPatent with realistic draft + reports."""
    return FinalPatent(
        task_id=task_id,
        patent_draft=_make_draft(),
        review_report=_make_review_report(),
        retrieval_report=_make_retrieval_report(),
        quality_score=0.9,
    )


# ── Generator Unit Tests ─────────────────────────────────────────────────────


class TestGenerateDocx:
    """generate_patent_docx with all input forms."""

    def test_with_dict(self, tmp_path: Path):
        """Accepts plain dict (the API endpoint code path)."""
        draft = _make_draft()
        filepath = generate_patent_docx(draft.model_dump(), "dict-test", tmp_path)
        assert Path(filepath).exists()
        doc_size = Path(filepath).stat().st_size
        assert doc_size > 10000, f"DOCX too small: {doc_size} bytes"

    def test_with_patent_draft(self, tmp_path: Path):
        """Accepts PatentDraft directly."""
        draft = _make_draft()
        filepath = generate_patent_docx(draft, "draft-test", tmp_path)
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 10000

    def test_with_final_patent(self, tmp_path: Path):
        """Accepts FinalPatent directly, derives task_id from FinalPatent."""
        fp = _make_final_patent("fp-test")
        filepath = generate_patent_docx(fp, fp.task_id, tmp_path)
        assert Path(filepath).exists()
        doc_size = Path(filepath).stat().st_size
        assert doc_size > 10000, f"DOCX too small: {doc_size} bytes"

    def test_with_patent_task_and_final_patent(self, tmp_path: Path):
        """Accepts (PatentTask, FinalPatent) pair."""
        fp = _make_final_patent("pt-fp-test")
        pt = PatentTask(
            task_id="pt-fp-test",
            user_id="test_user",
            tech_description="test",
            current_state=WorkflowState.COMPLETED,
        )
        filepath = generate_patent_docx(pt, fp, tmp_path)
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 10000

    def test_empty_claims_handling(self, tmp_path: Path):
        """Handles draft with empty claims list gracefully (no crash, produces doc)."""
        draft = PatentDraft(
            title="测试专利",
            technical_field="测试领域",
            background_art=DescriptionSection(section_name="背景技术", content="背景技术描述"),
            summary_of_invention=DescriptionSection(section_name="发明内容", content="发明内容描述"),
            description_of_drawings=None,
            detailed_description=DescriptionSection(section_name="具体实施方式", content="具体实施方式描述"),
            claims=[],
            abstract="摘要描述",
        )
        filepath = generate_patent_docx(draft.model_dump(), "empty-claims", tmp_path)
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 5000

    def test_invalid_type_raises(self):
        """Raises TypeError for unsupported patent_data types."""
        with pytest.raises(TypeError, match="Unsupported patent_data type"):
            generate_patent_docx(42, "invalid")  # type: ignore[arg-type]


# ── API Export Endpoint Tests ────────────────────────────────────────────────


class TestExportEndpoint:
    """GET /api/v1/export/{task_id} integration tests."""

    def test_export_with_final_patent(self, client, api_prefix):
        """Returns DOCX FileResponse for a completed task with final_patent."""
        from src.api.routes import tasks_store as ts

        fp = _make_final_patent("e2e-export-test")
        pt = PatentTask(
            task_id="e2e-export-test",
            user_id="test_user",
            tech_description="test",
            current_state=WorkflowState.COMPLETED,
            final_patent=fp,
        )
        ts["e2e-export-test"] = pt
        try:
            resp = client.get(f"{api_prefix}/export/e2e-export-test")
            assert resp.status_code == 200, f"Export failed: {resp.text[:200]}"
            ct = resp.headers.get("content-type", "")
            assert "vnd.openxmlformats" in ct, f"Unexpected content-type: {ct}"
            assert len(resp.content) > 10000, f"DOCX too small: {len(resp.content)} bytes"
        finally:
            ts.pop("e2e-export-test", None)
            shutil.rmtree(Path("backend/exports/e2e-export-test"), ignore_errors=True)

    def test_export_draft_doc_fallback(self, client, api_prefix):
        """Exports from draft_doc when final_patent is not set."""
        from src.api.routes import tasks_store as ts

        draft = _make_draft()
        pt = PatentTask(
            task_id="e2e-draft-fallback",
            user_id="test_user",
            tech_description="test",
            current_state=WorkflowState.WRITING,
            draft_doc=draft,
        )
        ts["e2e-draft-fallback"] = pt
        try:
            resp = client.get(f"{api_prefix}/export/e2e-draft-fallback")
            assert resp.status_code == 200, f"Export failed: {resp.text[:200]}"
            assert len(resp.content) > 10000
        finally:
            ts.pop("e2e-draft-fallback", None)
            shutil.rmtree(Path("backend/exports/e2e-draft-fallback"), ignore_errors=True)

    def test_export_404(self, client, api_prefix):
        """Returns 404 for unknown task_id."""
        resp = client.get(f"{api_prefix}/export/nonexistent")
        assert resp.status_code == 404

    def test_export_no_patent_data(self, client, api_prefix):
        """Returns 400 for a task without final_patent or draft_doc."""
        from src.api.routes import tasks_store as ts

        pt = PatentTask(
            task_id="e2e-no-data",
            user_id="test_user",
            tech_description="test",
            current_state=WorkflowState.INITIAL,
        )
        ts["e2e-no-data"] = pt
        try:
            resp = client.get(f"{api_prefix}/export/e2e-no-data")
            assert resp.status_code == 400
        finally:
            ts.pop("e2e-no-data", None)
