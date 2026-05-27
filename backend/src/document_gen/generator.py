"""
Patent document generator — produces professionally formatted .docx files
from FinalPatent data using python-docx.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from src.models.domain import (
    Claim,
    FinalPatent,
    PatentDraft,
    PatentTask,
)

EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / "exports"


def make_paragraph(doc: Document, text: str, bold: bool = False,
                   size: int = 12, alignment: Optional[int] = None,
                   font_name: str = "宋体", space_after: Optional[Cm] = None,
                   space_before: Optional[Cm] = None,
                   first_line_indent: Optional[Cm] = None) -> None:
    """Add a paragraph with proper CJK font handling."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.name = font_name
    run.bold = bold
    # Set East-Asian font for CJK characters
    run.element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    if alignment is not None:
        p.alignment = alignment
    if space_after is not None:
        p.paragraph_format.space_after = space_after
    if space_before is not None:
        p.paragraph_format.space_before = space_before
    if first_line_indent is not None:
        p.paragraph_format.first_line_indent = first_line_indent


def add_heading_cjk(doc: Document, text: str, level: int = 1) -> None:
    """Add a heading with proper CJK font."""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.name = "黑体"
        run.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        if level == 1:
            run.font.size = Pt(16)
        elif level == 2:
            run.font.size = Pt(14)
        else:
            run.font.size = Pt(12)


def add_section_heading(doc: Document, text: str) -> None:
    """Add a section heading (centered, bold) like 权利要求书, 说明书."""
    make_paragraph(
        doc, text, bold=True, size=18,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="黑体", space_before=Cm(2.0), space_after=Cm(1.0),
    )


def add_subsection_heading(doc: Document, text: str) -> None:
    """Add a subsection heading like 技术领域, 背景技术."""
    make_paragraph(
        doc, text, bold=True, size=14,
        font_name="黑体", space_before=Cm(0.8), space_after=Cm(0.4),
    )


def add_body_text(doc: Document, text: str, first_line_indent: Cm = Cm(0.74)) -> None:
    """Add body text with first-line indent (2 Chinese characters at 12pt)."""
    make_paragraph(
        doc, text, size=12, font_name="宋体",
        first_line_indent=first_line_indent,
        space_after=Cm(0.2),
    )


def build_claims_section(doc: Document, draft: PatentDraft) -> None:
    """Generate 权利要求书 section."""
    add_section_heading(doc, "权利要求书")

    # Add title line
    add_body_text(doc, f"1、{draft.title}")

    if not draft.claims:
        add_body_text(doc, "（无权利要求内容）")
        return

    for claim in draft.claims:
        text = _format_claim(claim)
        add_body_text(doc, text)


def _format_claim(claim: Claim) -> str:
    """Format a claim number + content with dependency reference."""
    prefix = f"{claim.claim_number}、"
    if claim.dependencies:
        dep_ref = "、".join(str(d) for d in claim.dependencies)
        prefix = f"{claim.claim_number}、根据权利要求{dep_ref}所述的"
    return f"{prefix}{claim.content}"


def build_description_section(doc: Document, draft: PatentDraft) -> None:
    """Generate 说明书 section."""
    add_section_heading(doc, "说  明  书")

    # 发明名称
    add_subsection_heading(doc, "发明名称")
    add_body_text(doc, draft.title)

    # 技术领域
    add_subsection_heading(doc, "技术领域")
    add_body_text(doc, draft.technical_field)

    # 背景技术
    add_subsection_heading(doc, "背景技术")
    add_body_text(doc, draft.background_art.content)

    # 发明内容
    add_subsection_heading(doc, "发明内容")
    add_body_text(doc, draft.summary_of_invention.content)

    # 附图说明 (optional)
    if draft.description_of_drawings:
        add_subsection_heading(doc, "附图说明")
        add_body_text(doc, draft.description_of_drawings.content)

    # 具体实施方式
    add_subsection_heading(doc, "具体实施方式")
    add_body_text(doc, draft.detailed_description.content)

    # 权利要求支持 (引用 claims 列表)
    if draft.claims:
        add_subsection_heading(doc, "权利要求书支持")
        add_body_text(doc, f"本说明书支持权利要求{len(draft.claims)}项所述的{len([c for c in draft.claims if c.claim_type == 'independent'])}个独立权利要求的技术方案。")


def build_abstract_section(doc: Document, draft: PatentDraft) -> None:
    """Generate 说明书摘要 section."""
    add_section_heading(doc, "说明书摘要")
    add_body_text(doc, draft.abstract)


def add_footer(doc: Document, task_id: str) -> None:
    """Add document metadata footer."""
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        run = p.add_run(f"专利智脑 · 任务 {task_id} · 生成时间 {now}")
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(128, 128, 128)
        run.font.name = "宋体"
        run.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def page_margin_default(doc: Document) -> None:
    """Set standard page margins for patent documents."""
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.17)
        section.right_margin = Cm(3.17)


def generate_patent_docx(
    patent_data: Dict[str, Any] | PatentTask | FinalPatent | PatentDraft,
    task_id_or_patent: str | FinalPatent | None = None,
    output_dir: Optional[Path] = None,
) -> str:
    """
    Generate a professional Chinese patent application .docx file.

    Accepts data in multiple compressed forms:
    - (dict, task_id)         — raw dict from API store + task ID string
    - (PatentTask, FinalPatent) — model objects from workflow engine
    - (PatentDraft, task_id)   — draft model + task ID string

    Args:
        patent_data: Dict or model containing patent draft data.
        task_id_or_patent: Task ID string or FinalPatent (for model path).
        output_dir: Directory to save the file (defaults to EXPORT_DIR/task_id/).

    Returns:
        Absolute path to the generated .docx file.
    """
    # Normalize inputs to (draft_dict, task_id)
    if isinstance(patent_data, dict):
        draft_dict: dict = patent_data
        task_id: str = task_id_or_patent  # type: ignore[assignment]
    elif isinstance(patent_data, FinalPatent):
        draft_dict = patent_data.patent_draft.model_dump()
        task_id = patent_data.task_id
    elif isinstance(patent_data, PatentTask):
        fp = task_id_or_patent
        assert isinstance(fp, FinalPatent), "PatentTask needs FinalPatent as second arg"
        draft_dict = fp.patent_draft.model_dump()
        task_id = patent_data.task_id
    elif isinstance(patent_data, PatentDraft):
        draft_dict = patent_data.model_dump()
        task_id = task_id_or_patent  # type: ignore[assignment]
    else:
        raise TypeError(f"Unsupported patent_data type: {type(patent_data)}")

    # Parse draft dict through Pydantic for validation + nested model coercion
    draft = PatentDraft(**draft_dict)

    if output_dir is None:
        output_dir = EXPORT_DIR / task_id
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    file_path = output_dir / f"{task_id}_专利申请书.docx"

    doc = Document()
    page_margin_default(doc)

    # ── Title page ──
    make_paragraph(
        doc, "专利申请文件", bold=True, size=22,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="黑体", space_after=Cm(3.0),
    )
    make_paragraph(
        doc, draft.title, bold=True, size=16,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="黑体", space_after=Cm(1.0),
    )
    make_paragraph(
        doc, f"任务编号：{task_id}", size=10,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="宋体", space_after=Cm(0.3),
    )
    make_paragraph(
        doc, f"专利类型：{draft.claims[0].category if draft.claims else '发明专利'}",
        size=10, alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="宋体", space_after=Cm(2.0),
    )

    # ── 权利要求书 (page break) ──
    doc.add_page_break()
    build_claims_section(doc, draft)

    # ── 说明书 (page break) ──
    doc.add_page_break()
    build_description_section(doc, draft)

    # ── 说明书摘要 (page break) ──
    doc.add_page_break()
    build_abstract_section(doc, draft)

    # ── Footer ──
    add_footer(doc, task_id)

    doc.save(str(file_path))
    return str(file_path)
