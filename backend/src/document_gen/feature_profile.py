"""
Patent Feature Profile — a complete, serializable description of formatting
and content characteristics extracted from finalized patent documents.

This profile is extracted ONCE from reference documents and persisted as JSON.
The generator uses this profile (not the original docx files) to produce output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PageLayout:
    """Page size and margins extracted from reference patents."""

    # Page dimensions (cm)
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7

    # Per-section margins: (top, bottom, left, right) in cm
    # Each document has 5 sections in order:
    #   摘要, 摘要附图, 权利要求书, 说明书, 说明书附图
    margins_abstract: Tuple[float, float, float, float] = (2.60, 2.00, 2.80, 1.80)
    margins_abstract_drawings: Tuple[float, float, float, float] = (2.60, 2.00, 2.60, 2.00)
    margins_claims: Tuple[float, float, float, float] = (2.60, 2.00, 2.60, 2.00)
    margins_description: Tuple[float, float, float, float] = (2.60, 2.00, 2.80, 1.80)
    margins_description_drawings: Tuple[float, float, float, float] = (2.60, 2.00, 2.80, 1.80)


@dataclass
class Typography:
    """Font and text styling features."""

    # Body text
    body_font_name: str = "楷体"
    body_font_size_pt: float = 14.0
    body_bold: bool = False

    # Section sub-headings (技术领域, 背景技术, etc.)
    section_heading_font_name: str = "楷体"
    section_heading_font_size_pt: float = 14.0
    section_heading_bold: bool = True

    # Document-level headings (权利要求书, 说明书, etc.)
    doc_heading_font_name: str = "楷体"
    doc_heading_bold: bool = False
    doc_heading_char_spacing: bool = True  # chars are spaced apart


@dataclass
class ParagraphFormat:
    """Paragraph-level formatting features."""

    # Body paragraphs
    body_first_line_indent_cm: float = 0.99
    body_line_spacing_emu: int = 292100  # ~23pt fixed line spacing
    body_alignment: str = "JUSTIFY"  # JUSTIFY | LEFT | CENTER

    # Section headings
    section_heading_alignment: str = "JUSTIFY"
    section_heading_indent_cm: float = 0.0  # no indent for headings

    # Document headings
    doc_heading_alignment: str = "CENTER"


@dataclass
class DocumentStructure:
    """Structural features of the patent document."""

    # Section order (all patents follow this)
    section_order: List[str] = field(default_factory=lambda: [
        "说明书摘要",
        "摘要附图",
        "权利要求书",
        "说明书",
        "说明书附图",
    ])

    # Description sub-sections (all patents follow this order)
    description_sections: List[str] = field(default_factory=lambda: [
        "技术领域",
        "背景技术",
        "发明内容",
        "附图说明",
        "具体实施方式",
    ])

    # Number of document sections (page breaks)
    num_sections: int = 5

    # Heading text patterns (spaced characters)
    heading_char_separator: str = "    "  # 4 spaces between chars


@dataclass
class ContentPatterns:
    """Writing style and content structure patterns."""

    # Claim patterns
    claim_independent_prefix: str = "其特征在于"
    claim_dependent_format: str = "根据权利要求{n}所述的"
    claim_numbering_separator: str = "、"  # e.g. "1、"

    # Description opening patterns
    tech_field_opening: str = "本发明涉及"
    background_transition: str = "然而"
    invention_summary_opening: str = "为解决上述技术问题"
    detailed_desc_opening: str = "为使本发明实施例的目的、技术方案和优点更加清楚"
    detailed_desc_explanation_marker: str = "需要说明的是"
    detailed_desc_closing: str = "最后应说明的是"

    # Abstract pattern
    abstract_opening: str = "本发明提供一种"

    # Average structural metrics (from analysis of all reference patents)
    avg_claims_count: float = 10.0
    avg_independent_claims: float = 1.0
    avg_claim_length_chars: float = 80.0
    avg_description_total_chars: float = 10000.0
    avg_abstract_length_chars: float = 250.0


@dataclass
class DisclosureFormat:
    """
    A-file (交底书/对话记录) formatting characteristics.

    A-files are fundamentally different from B-files:
    - They are raw conversation transcripts between inventors
    - They serve as input material for LLM content generation
    - They do NOT define the output format (B-files do)

    These features describe A-file structure for proper parsing.
    """

    # Page layout (Letter size, not A4)
    page_width_cm: float = 21.59
    page_height_cm: float = 27.94
    margins: Tuple[float, float, float, float] = (2.54, 2.54, 3.17, 3.17)

    # Document structure
    num_sections: int = 1  # Single section (no page breaks)
    styles_used: List[str] = field(default_factory=lambda: ["Normal"])

    # Typography
    font_name: str = ""  # No explicit font (system default)
    font_size_pt: float = 0.0  # No explicit size
    has_explicit_formatting: bool = False

    # Content characteristics
    content_type: str = "对话记录"  # 对话记录 | 技术描述
    has_timestamps: bool = True  # Format: A(HH:MM:SS): or B(HH:MM:SS):
    has_speaker_labels: bool = True  # A/B speaker identifiers
    timestamp_format: str = r"^[AB]\(\d{2}:\d{2}:\d{2}\)"
    avg_paragraph_length_chars: float = 70.0
    avg_paragraph_count: float = 75.0

    # No structural headings (unlike B-files)
    has_headings: bool = False
    has_first_line_indent: bool = False
    alignment: str = "LEFT"  # Default left alignment


@dataclass
class PatentFeatureProfile:
    """
    Complete feature profile extracted from finalized patent documents.

    This is the single source of truth for patent document formatting and style.
    It is extracted once, persisted as JSON, and used by the generator.
    """

    # Version for schema evolution
    version: str = "1.0"

    # Source metadata
    source_dir: str = ""
    num_patents_analyzed: int = 0
    extraction_date: str = ""

    # Feature groups
    page_layout: PageLayout = field(default_factory=PageLayout)
    typography: Typography = field(default_factory=Typography)
    paragraph_format: ParagraphFormat = field(default_factory=ParagraphFormat)
    document_structure: DocumentStructure = field(default_factory=DocumentStructure)
    content_patterns: ContentPatterns = field(default_factory=ContentPatterns)
    disclosure_format: DisclosureFormat = field(default_factory=DisclosureFormat)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (JSON-safe)."""
        return asdict(self)

    def save(self, path: Path) -> None:
        """Persist profile to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path) -> "PatentFeatureProfile":
        """Load profile from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatentFeatureProfile":
        """Reconstruct from dict."""
        return cls(
            version=data.get("version", "1.0"),
            source_dir=data.get("source_dir", ""),
            num_patents_analyzed=data.get("num_patents_analyzed", 0),
            extraction_date=data.get("extraction_date", ""),
            page_layout=PageLayout(**data.get("page_layout", {})),
            typography=Typography(**data.get("typography", {})),
            paragraph_format=ParagraphFormat(**data.get("paragraph_format", {})),
            document_structure=DocumentStructure(**data.get("document_structure", {})),
            content_patterns=ContentPatterns(**data.get("content_patterns", {})),
            disclosure_format=DisclosureFormat(**data.get("disclosure_format", {})),
        )


# Default profile path (persisted after extraction)
DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parent / "patent_feature_profile.json"
)


def load_profile(path: Optional[Path] = None) -> PatentFeatureProfile:
    """
    Load the feature profile from disk.
    Falls back to built-in defaults if no persisted profile exists.
    """
    target = path or DEFAULT_PROFILE_PATH
    if target.exists():
        return PatentFeatureProfile.load(target)
    # Return defaults (which match the reference patents)
    return PatentFeatureProfile()
