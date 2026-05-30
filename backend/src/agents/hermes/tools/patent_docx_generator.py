"""
Patent DOCX Generator Tool — 生成符合专利局规范的专利申请文件(.docx)

该工具被专利撰写Agent在完成文本撰写后调用，将结构化的专利内容
（权利要求书+说明书+摘要）转换为格式规范的.docx文件。

格式规范来自 PatentFeatureProfile（从定稿文件/中提取的格式特征）：
- 楷体14pt正文，首行缩进0.99cm
- A4页面，正确的各节页边距
- 文档标题字符间距展开（"权    利    要    求    书"）
- 说明书子标题加粗（技术领域、背景技术等）
- 权利要求编号格式："1、...其特征在于..."
"""
import json
import re
from pathlib import Path
from typing import Any, Dict


class PatentDocxGeneratorTool:
    """生成专利申请DOCX文件的工具"""

    name = "patent_docx_generator"
    description = "将结构化的专利撰写结果生成为符合专利局规范的.docx文件"

    async def execute(
        self,
        title: str = "专利申请文件",
        claims: Dict[str, Any] = None,
        description: Dict[str, Any] = None,
        abstract: str = "",
        task_id: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        生成专利DOCX文件

        Args:
            title: 专利标题
            claims: 权利要求 {"independent_claim": "...", "dependent_claims": ["..."]}
            description: 说明书 {"technical_field": "...", "background_art": "...", 
                         "summary_of_invention": "...", "detailed_description": "..."}
            abstract: 说明书摘要
            task_id: 任务ID（用于文件命名和存储路径）

        Returns:
            {"success": True, "file_path": "...", "message": "..."}
        """
        if not claims and not description and not abstract:
            return {"success": False, "error": "未提供任何专利内容，无法生成文件"}

        claims = claims or {}
        description = description or {}

        try:
            from src.document_gen.generator import (
                _strip_markdown,
                _get_profile,
                add_document_heading,
                add_section_heading,
                add_body_paragraph,
                _add_multiline_content,
                add_new_section,
                _set_page_size,
                _get_margins_for_section,
                _set_section_margins,
                _set_run_font,
            )
            from docx import Document
            from docx.shared import Pt

            profile = _get_profile()
            doc = Document()

            # 配置首页（摘要）
            first_section = doc.sections[0]
            _set_page_size(first_section, profile)
            margins = _get_margins_for_section("摘要", profile)
            _set_section_margins(first_section, margins)

            # ── 说明书摘要 ──
            add_document_heading(doc, "说明书摘要", profile)
            add_body_paragraph(doc, _strip_markdown(abstract) if abstract else "（待补充）", profile)

            # ── 摘要附图 ──
            add_new_section(doc, "摘要附图", profile)
            add_document_heading(doc, "摘要附图", profile)
            add_body_paragraph(doc, "（无附图）", profile, first_line_indent=False)

            # ── 权利要求书 ──
            add_new_section(doc, "权利要求书", profile)
            add_document_heading(doc, "权利要求书", profile)

            if claims:
                ind_claim = _strip_markdown(claims.get("independent_claim", ""))
                if ind_claim:
                    # 去除LLM生成的编号前缀
                    ind_claim = re.sub(r'^\d+[\.\、]\s*', '', ind_claim.strip())
                    add_body_paragraph(doc, f"1、{ind_claim}", profile)

                for i, dep in enumerate(claims.get("dependent_claims", []), 2):
                    dep_text = _strip_markdown(dep)
                    dep_text = re.sub(r'^\d+[\.\、]\s*', '', dep_text.strip())
                    add_body_paragraph(doc, f"{i}、{dep_text}", profile)
            else:
                add_body_paragraph(doc, "（待补充权利要求）", profile)

            # ── 说明书 ──
            add_new_section(doc, "说明书", profile)
            add_document_heading(doc, "说明书", profile)

            # 专利名称（16pt楷体）
            title_para = doc.add_paragraph()
            title_run = title_para.add_run(_strip_markdown(title))
            _set_run_font(title_run, "楷体", 16.0)

            # 技术领域
            add_section_heading(doc, "技术领域", profile)
            tech_field = description.get("technical_field", "")
            _add_multiline_content(doc, tech_field if tech_field else "（待补充）", profile)

            # 背景技术
            add_section_heading(doc, "背景技术", profile)
            bg = description.get("background_art", "")
            _add_multiline_content(doc, bg if bg else "（待补充）", profile)

            # 发明内容
            add_section_heading(doc, "发明内容", profile)
            summary = description.get("summary_of_invention", "")
            _add_multiline_content(doc, summary if summary else "（待补充）", profile)

            # 附图说明（可选）
            drawings_desc = description.get("description_of_drawings", "")
            if drawings_desc:
                add_section_heading(doc, "附图说明", profile)
                _add_multiline_content(doc, drawings_desc, profile)

            # 具体实施方式
            add_section_heading(doc, "具体实施方式", profile)
            detailed = description.get("detailed_description", "")
            _add_multiline_content(doc, detailed if detailed else "（待补充）", profile)

            # ── 说明书附图 ──
            add_new_section(doc, "说明书附图", profile)
            add_document_heading(doc, "说明书附图", profile)
            add_body_paragraph(doc, "（无附图）", profile, first_line_indent=False)

            # 保存文件
            export_dir = Path("./exports") / (task_id or "default")
            export_dir.mkdir(parents=True, exist_ok=True)

            # 文件名使用专利标题
            safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50]
            file_path = export_dir / f"{safe_title}.docx"
            doc.save(str(file_path))

            return {
                "success": True,
                "file_path": str(file_path),
                "file_name": f"{safe_title}.docx",
                "message": f"专利申请文件已生成：{file_path}",
                "sections": ["说明书摘要", "摘要附图", "权利要求书", "说明书", "说明书附图"],
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"生成DOCX文件失败：{str(e)}",
            }
