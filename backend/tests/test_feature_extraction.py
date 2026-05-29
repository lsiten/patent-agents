"""
Tests for patent feature extraction.

Validates that features extracted from the 定稿文件/ directory
accurately reflect the actual content of each finalized patent docx.

Test strategy:
1. Extract profile from all B-files → verify aggregated values are correct
2. For EACH individual B-file → verify extracted features match the actual docx
3. Verify profile persistence (save/load round-trip)
"""

import re
import statistics
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

from src.document_gen.feature_extractor import (
    _extract_content_patterns,
    _extract_document_structure,
    _extract_page_layout,
    _extract_paragraph_format,
    _extract_typography,
    extract_profile,
)
from src.document_gen.feature_profile import PatentFeatureProfile

# Path to finalized patents (project root)
FINALIZED_DIR = Path(__file__).resolve().parent.parent.parent / "定稿文件"

# Skip all tests if the directory doesn't exist (CI without reference files)
pytestmark = pytest.mark.skipif(
    not FINALIZED_DIR.exists(),
    reason="定稿文件 directory not found",
)


def _get_all_b_files() -> list:
    """Collect all B-*.docx files."""
    files = []
    for subdir in sorted(FINALIZED_DIR.iterdir()):
        if subdir.is_dir():
            for f in subdir.glob("B-*.docx"):
                files.append(f)
    return files


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Aggregated Profile
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregatedProfile:
    """Tests on the overall extracted profile."""

    @pytest.fixture(scope="class")
    def profile(self) -> PatentFeatureProfile:
        return extract_profile(FINALIZED_DIR)

    def test_profile_analyzes_all_files(self, profile):
        """Profile should analyze all available B-files."""
        b_files = _get_all_b_files()
        assert profile.num_patents_analyzed == len(b_files)
        assert profile.num_patents_analyzed >= 10  # We know there are 12

    # ─── Page Layout ─────────────────────────────────────────────────────

    def test_page_size_is_a4(self, profile):
        """All reference patents use A4 page size."""
        assert profile.page_layout.page_width_cm == 21.0
        assert profile.page_layout.page_height_cm == 29.7

    def test_margins_abstract_section(self, profile):
        """摘要 section margins match reference."""
        m = profile.page_layout.margins_abstract
        assert m[0] == pytest.approx(2.60, abs=0.05)  # top
        assert m[1] == pytest.approx(2.00, abs=0.05)  # bottom
        assert m[2] == pytest.approx(2.80, abs=0.05)  # left
        assert m[3] == pytest.approx(1.80, abs=0.05)  # right

    def test_margins_claims_section(self, profile):
        """权利要求书 section margins match reference."""
        m = profile.page_layout.margins_claims
        assert m[0] == pytest.approx(2.60, abs=0.05)
        assert m[1] == pytest.approx(2.00, abs=0.05)
        assert m[2] == pytest.approx(2.60, abs=0.05)
        assert m[3] == pytest.approx(2.00, abs=0.05)

    def test_margins_description_section(self, profile):
        """说明书 section margins match reference."""
        m = profile.page_layout.margins_description
        assert m[0] == pytest.approx(2.60, abs=0.05)
        assert m[1] == pytest.approx(2.00, abs=0.05)
        assert m[2] == pytest.approx(2.80, abs=0.05)
        assert m[3] == pytest.approx(1.80, abs=0.05)

    # ─── Typography ──────────────────────────────────────────────────────

    def test_body_font_is_kaiti(self, profile):
        """Body text uses 楷体 font."""
        assert profile.typography.body_font_name == "楷体"

    def test_body_font_size_14pt(self, profile):
        """Body text is 14pt."""
        assert profile.typography.body_font_size_pt == pytest.approx(14.0, abs=0.5)

    def test_section_heading_bold(self, profile):
        """Section sub-headings are bold."""
        assert profile.typography.section_heading_bold is True

    def test_doc_heading_font(self, profile):
        """Document-level headings use 楷体."""
        assert profile.typography.doc_heading_font_name == "楷体"

    def test_doc_heading_char_spacing(self, profile):
        """Document headings have spaced characters."""
        assert profile.typography.doc_heading_char_spacing is True

    # ─── Paragraph Format ────────────────────────────────────────────────

    def test_first_line_indent(self, profile):
        """Body paragraphs have ~1cm first line indent."""
        assert profile.paragraph_format.body_first_line_indent_cm == pytest.approx(
            0.99, abs=0.15
        )

    def test_line_spacing(self, profile):
        """Line spacing is ~292100 EMU (fixed ~23pt)."""
        assert profile.paragraph_format.body_line_spacing_emu == pytest.approx(
            292100, abs=5000
        )

    def test_body_alignment_justify(self, profile):
        """Body text is justified."""
        assert "JUSTIFY" in profile.paragraph_format.body_alignment.upper()

    def test_doc_heading_center(self, profile):
        """Document headings are centered."""
        assert profile.paragraph_format.doc_heading_alignment == "CENTER"

    # ─── Document Structure ──────────────────────────────────────────────

    def test_five_sections(self, profile):
        """Document has 5 sections."""
        assert profile.document_structure.num_sections == 5

    def test_section_order(self, profile):
        """Sections follow standard patent order."""
        expected = ["说明书摘要", "摘要附图", "权利要求书", "说明书", "说明书附图"]
        assert profile.document_structure.section_order == expected

    def test_description_subsections(self, profile):
        """Description has all 5 standard sub-sections."""
        expected = {"技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式"}
        actual = set(profile.document_structure.description_sections)
        assert expected == actual

    # ─── Content Patterns ────────────────────────────────────────────────

    def test_claim_characteristic_marker(self, profile):
        """Independent claims use '其特征在于'."""
        assert "其特征在于" in profile.content_patterns.claim_independent_prefix

    def test_claim_dependent_format(self, profile):
        """Dependent claims use '根据权利要求...'."""
        assert "根据权利要求" in profile.content_patterns.claim_dependent_format

    def test_abstract_opening(self, profile):
        """Abstract starts with '本发明提供一种' or '本发明'."""
        assert "本发明" in profile.content_patterns.abstract_opening

    def test_explanation_marker(self, profile):
        """Detailed description uses '需要说明的是'."""
        assert "需要说明的是" in profile.content_patterns.detailed_desc_explanation_marker

    def test_avg_claims_reasonable(self, profile):
        """Average claims count is reasonable (5-15)."""
        assert 5 <= profile.content_patterns.avg_claims_count <= 15

    def test_avg_abstract_length(self, profile):
        """Average abstract is 150-400 chars."""
        assert 150 <= profile.content_patterns.avg_abstract_length_chars <= 400


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Per-file Feature Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestPerFileFeatures:
    """Verify that features extracted from EACH B-file match its actual content."""

    @pytest.fixture(params=_get_all_b_files(), ids=lambda f: f.parent.name)
    def b_file_doc(self, request) -> tuple:
        """Parametrized fixture: (Path, Document) for each B-file."""
        path = request.param
        doc = Document(str(path))
        return path, doc

    def test_page_size_a4(self, b_file_doc):
        """Each file uses A4 page."""
        _, doc = b_file_doc
        layout = _extract_page_layout(doc)
        assert layout["page_width_cm"] == pytest.approx(21.0, abs=0.1)
        assert layout["page_height_cm"] == pytest.approx(29.7, abs=0.1)

    def test_has_five_sections(self, b_file_doc):
        """Each file has exactly 5 sections."""
        _, doc = b_file_doc
        structure = _extract_document_structure(doc)
        assert structure["num_sections"] == 5

    def test_body_font_kaiti(self, b_file_doc):
        """Each file uses 楷体 body font."""
        _, doc = b_file_doc
        typo = _extract_typography(doc)
        if typo["body_fonts"]:
            most_common_font = max(set(typo["body_fonts"]), key=typo["body_fonts"].count)
            assert most_common_font == "楷体"

    def test_body_font_size_14pt(self, b_file_doc):
        """Each file uses 14pt body text."""
        _, doc = b_file_doc
        typo = _extract_typography(doc)
        if typo["body_sizes"]:
            median_size = statistics.median(typo["body_sizes"])
            assert median_size == pytest.approx(14.0, abs=0.5)

    def test_first_line_indent_approx_1cm(self, b_file_doc):
        """Each file has ~1cm first line indent."""
        _, doc = b_file_doc
        para_fmt = _extract_paragraph_format(doc)
        if para_fmt["indents"]:
            median_indent = statistics.median(para_fmt["indents"])
            assert median_indent == pytest.approx(1.0, abs=0.2)

    def test_line_spacing_292100(self, b_file_doc):
        """Each file uses ~292100 EMU line spacing."""
        _, doc = b_file_doc
        para_fmt = _extract_paragraph_format(doc)
        if para_fmt["line_spacings"]:
            median_spacing = statistics.median(para_fmt["line_spacings"])
            assert median_spacing == pytest.approx(292100, abs=10000)

    def test_has_description_sections(self, b_file_doc):
        """Each file has standard description sub-sections."""
        _, doc = b_file_doc
        structure = _extract_document_structure(doc)
        sections = set(structure["description_sections"])
        # At minimum: 技术领域, 背景技术, 发明内容, 具体实施方式
        required = {"技术领域", "背景技术", "发明内容", "具体实施方式"}
        assert required.issubset(sections), f"Missing sections: {required - sections}"

    def test_has_claims(self, b_file_doc):
        """Each file has at least 1 claim."""
        _, doc = b_file_doc
        content = _extract_content_patterns(doc)
        assert content["num_claims"] >= 1

    def test_claims_use_characteristic_marker(self, b_file_doc):
        """Claims use '其特征在于' marker."""
        _, doc = b_file_doc
        content = _extract_content_patterns(doc)
        assert content["has_characteristic_marker"] is True

    def test_section_margins_top(self, b_file_doc):
        """Each section has top margin ~2.6cm."""
        _, doc = b_file_doc
        layout = _extract_page_layout(doc)
        for margins in layout["section_margins"][:5]:
            assert margins[0] == pytest.approx(2.60, abs=0.1)

    def test_section_margins_bottom(self, b_file_doc):
        """Each section has bottom margin ~2.0cm."""
        _, doc = b_file_doc
        layout = _extract_page_layout(doc)
        for margins in layout["section_margins"][:5]:
            assert margins[1] == pytest.approx(2.00, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Profile Persistence
# ═══════════════════════════════════════════════════════════════════════════════


class TestProfilePersistence:
    """Test save/load round-trip."""

    def test_save_and_load(self, tmp_path):
        """Profile survives JSON round-trip."""
        profile = extract_profile(FINALIZED_DIR)
        save_path = tmp_path / "profile.json"
        profile.save(save_path)

        loaded = PatentFeatureProfile.load(save_path)

        # Verify key fields survive
        assert loaded.num_patents_analyzed == profile.num_patents_analyzed
        assert loaded.page_layout.page_width_cm == profile.page_layout.page_width_cm
        assert loaded.typography.body_font_name == profile.typography.body_font_name
        assert loaded.typography.body_font_size_pt == profile.typography.body_font_size_pt
        assert loaded.paragraph_format.body_first_line_indent_cm == profile.paragraph_format.body_first_line_indent_cm
        assert loaded.paragraph_format.body_line_spacing_emu == profile.paragraph_format.body_line_spacing_emu
        assert loaded.document_structure.num_sections == profile.document_structure.num_sections
        assert loaded.content_patterns.claim_independent_prefix == profile.content_patterns.claim_independent_prefix

    def test_profile_json_is_readable(self, tmp_path):
        """Saved JSON is human-readable (not minified, has Chinese)."""
        profile = extract_profile(FINALIZED_DIR)
        save_path = tmp_path / "profile.json"
        profile.save(save_path)

        content = save_path.read_text(encoding="utf-8")
        assert "楷体" in content  # Chinese preserved
        assert "\n" in content  # Pretty-printed
        assert "body_font_name" in content  # Field names present
