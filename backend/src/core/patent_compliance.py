# -*- coding: utf-8 -*-
"""Deterministic patent drafting compliance helpers.

These helpers intentionally do not judge patentability or drafting quality.
They only check rules that can be verified mechanically, so Hermes Agents can
use the findings as objective signals and still make the professional decision.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


TRANSCRIPT_ARTIFACT_RE = re.compile(
    r"[\u4e00-\u9fa5A-Za-z0-9_·（）()、\s]{1,30}[（(]\d{2}:\d{2}:\d{2}[）)]\s*[：:]?"
)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
CLAIM_LINE_RE = re.compile(r"(?:^|\n)\s*(\d+)[\.、]\s*")
FIGURE_REF_RE = re.compile(r"图\s*([0-9]{1,2})")


def sanitize_transcript_text(text: str) -> Dict[str, Any]:
    """Remove transcript wrappers while preserving technical content."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: List[str] = []
    removed = 0
    speaker_ts = re.compile(
        r"^\s*[\u4e00-\u9fa5A-Za-z0-9_·（）()、\s]{1,30}[（(]\d{2}:\d{2}:\d{2}[）)]\s*[：:]?\s*"
    )
    plain_ts = re.compile(r"^\s*[（(]?\d{2}:\d{2}:\d{2}[）)]?\s*[：:]?\s*")
    filename_noise = re.compile(r"^\s*(文件名|任务编号|生成时间|逐字稿|会议记录|转写文本)\s*[：:]")
    conversational_noise = re.compile(
        r"^(这样)?我(先|来)?开个头[！!。.]?$|^你说[。.]?$|^然后[。.]?$|^对写的时候.*$"
    )
    filler = {"嗯", "啊", "对", "行", "好的", "那先写", "那写吧"}

    for raw_line in raw.split("\n"):
        line = raw_line.strip()
        if not line or filename_noise.search(line):
            removed += 1
            continue
        before = line
        line = speaker_ts.sub("", line)
        line = plain_ts.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line != before:
            removed += 1
        if not line or line in filler or conversational_noise.match(line):
            removed += 1
            continue
        lines.append(line)

    cleaned = "\n".join(lines).strip()
    return {
        "cleaned_text": cleaned or raw.strip(),
        "removed_line_count": removed,
        "had_transcript_artifacts": bool(TRANSCRIPT_ARTIFACT_RE.search(raw)),
    }


def split_claims_text(claims_text: str) -> List[str]:
    """Split a claims string into numbered claim blocks."""
    text = str(claims_text or "").strip()
    if not text:
        return []
    matches = list(CLAIM_LINE_RE.finditer(text))
    if not matches:
        return [text]

    claims: List[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            claims.append(block)
    return claims


def _find_claim_steps(independent_claim: str) -> List[str]:
    text = str(independent_claim or "")
    step_matches = list(re.finditer(r"(S\d+|步骤[一二三四五六七八九十A-D]|[A-D][、.．])", text))
    if step_matches:
        return [match.group(0) for match in step_matches]
    # When explicit step markers are absent, count technical actions after "包括".
    body = text.split("包括", 1)[-1] if "包括" in text else text
    parts = [part.strip() for part in re.split(r"[；;。]\s*", body) if part.strip()]
    return parts


CLAIM_MANDATORY_LINEBREAK_PUNCT_RE = re.compile(r"[；;。]|(?<!\d)\.")
SECONDARY_INDEPENDENT_CLAIM_RE = re.compile(
    r"^\s*\d+[\.\、]\s*一种.+?(系统|装置|设备|介质|计算机程序产品|终端|服务器)，"
)


def _is_secondary_independent_claim(block: str) -> bool:
    """Return True for system/device/storage claims that are not dependent claims."""
    text = str(block or "").strip()
    if not text:
        return False
    if re.search(r"根据\s*权利要求\s*\d+", text):
        return False
    return bool(SECONDARY_INDEPENDENT_CLAIM_RE.search(text))


def _claims_contain_secondary_subject(claims: Any, subjects: Iterable[str]) -> bool:
    """Return True when claims include an additional independent subject claim."""
    subject_tuple = tuple(subjects)
    if not subject_tuple:
        return True
    if isinstance(claims, dict):
        candidates = claims.get("dependent_claims") or []
        if not isinstance(candidates, list):
            candidates = [candidates]
    else:
        blocks = split_claims_text(str(claims or ""))
        candidates = blocks[1:]
    for item in candidates:
        block = str(item or "")
        if any(subject in block for subject in subject_tuple) and _is_secondary_independent_claim(block):
            return True
    return False


def normalize_claim_linebreaks(claim_text: str) -> str:
    """Force a newline after semicolons and sentence-ending periods in claims."""
    text = str(claim_text or "").strip()
    if not text:
        return ""
    text = re.sub(r"([；;。]|(?<!\d)\.)\s*", r"\1\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def validate_claim_rules(claims: Any) -> Dict[str, Any]:
    """Validate hard claim rules required by the patent drafting manual."""
    if isinstance(claims, dict):
        independent = str(claims.get("independent_claim") or "")
        dependent_raw = claims.get("dependent_claims") or []
        dependent = (
            [str(item) for item in dependent_raw if str(item).strip()]
            if isinstance(dependent_raw, list)
            else [str(dependent_raw)] if str(dependent_raw or "").strip() else []
        )
        claims_text = "\n".join([independent, *dependent])
    else:
        claims_text = str(claims or "")
        blocks = split_claims_text(claims_text)
        independent = blocks[0] if blocks else ""
        dependent = blocks[1:]

    issues: List[Dict[str, Any]] = []
    claim_blocks = [independent, *dependent]

    if not independent.strip():
        issues.append({
            "severity": "critical",
            "location": "权利要求1",
            "issue": "缺少独立权利要求",
            "suggestion": "由专利撰写 Agent 重写权利要求1。",
            "target_agent": "patent_writer",
        })
    else:
        step_count = len(_find_claim_steps(independent))
        if step_count not in (3, 4):
            issues.append({
                "severity": "critical",
                "location": "权利要求1",
                "issue": f"独立权利要求不是3步或4步结构，当前识别为{step_count}步",
                "suggestion": "将独立权利要求重构为S1-S3或S1-S4，每步承接前一步输出。",
                "target_agent": "patent_writer",
            })
        if len(independent) > 250:
            issues.append({
                "severity": "high",
                "location": "权利要求1",
                "issue": f"独立权利要求超过250字，当前约{len(independent)}字",
                "suggestion": "删除实施例细节和非必要参数，保留必要技术特征。",
                "target_agent": "patent_writer",
            })
    if not dependent:
        issues.append({
            "severity": "critical",
            "location": "权利要求书",
            "issue": "缺少从属权利要求",
            "suggestion": "权利要求书必须由独立权利要求和从属权利要求组成。",
            "target_agent": "patent_writer",
        })

    for idx, block in enumerate(claim_blocks, start=1):
        is_secondary_independent = idx > 1 and _is_secondary_independent_claim(block)
        if idx > 1 and not is_secondary_independent and len(block) > 200:
            issues.append({
                "severity": "high",
                "location": f"权利要求{idx}",
                "issue": f"从属权利要求超过200字，当前约{len(block)}字",
                "suggestion": "删减实施例细节和非必要限定，保留该从属权利要求的单一附加特征。",
                "target_agent": "patent_writer",
            })
        for match in CLAIM_MANDATORY_LINEBREAK_PUNCT_RE.finditer(block):
            following = block[match.end(): match.end() + 1]
            if following and following != "\n":
                issues.append({
                    "severity": "critical",
                    "location": f"权利要求{idx}",
                    "issue": "分号或句号后未换行",
                    "suggestion": "每个分号和句号后必须换行。",
                    "target_agent": "patent_writer",
                })
                break

    for idx, block in enumerate(dependent, start=2):
        if _is_secondary_independent_claim(block):
            continue
        ref_match = re.search(r"权利要求\s*([0-9]+)", block)
        if not ref_match:
            issues.append({
                "severity": "high",
                "location": f"权利要求{idx}",
                "issue": "从属权利要求缺少引用关系",
                "suggestion": "按“根据权利要求N所述的……”补充引用部分。",
                "target_agent": "patent_writer",
            })
            continue
        if int(ref_match.group(1)) >= idx:
            issues.append({
                "severity": "critical",
                "location": f"权利要求{idx}",
                "issue": "从属权利要求引用了自身或后序权利要求",
                "suggestion": "从属权利要求只能引用在前权利要求。",
                "target_agent": "patent_writer",
            })

    return {
        "passed": not any(item["severity"] in {"critical", "high"} for item in issues),
        "issues": issues,
        "metrics": {
            "claim_count": len([block for block in claim_blocks if str(block).strip()]),
            "dependent_claim_count": len(dependent),
            "independent_step_count": len(_find_claim_steps(independent)) if independent else 0,
            "independent_length": len(independent),
        },
    }


def _issue(
    issues: List[Dict[str, Any]],
    severity: str,
    location: str,
    issue: str,
    suggestion: str,
    target_agent: str = "patent_writer",
) -> None:
    issues.append({
        "severity": severity,
        "location": location,
        "issue": issue,
        "suggestion": suggestion,
        "target_agent": target_agent,
    })


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _title_referenced_in_abstract(title: str, abstract: str) -> bool:
    title = str(title or "").strip()
    abstract = str(abstract or "").strip()
    if not title or not abstract:
        return False
    if title in abstract:
        return True
    normalized_title = re.sub(r"^(一种|一项|一种用于|一种基于)", "", title)
    normalized_title = re.sub(r"(的方法|的系统|的装置|的设备|的介质|方法|系统|装置|设备)$", "", normalized_title)
    tokens = [
        token
        for token in re.split(r"[，,、；;：:\s及与和的]+", normalized_title)
        if len(token) >= 2
    ]
    if not tokens:
        tokens = [normalized_title[:8]] if len(normalized_title) >= 4 else []
    matched = sum(1 for token in tokens if token and token in abstract)
    return matched >= max(1, min(2, len(tokens)))


def validate_patent_manual_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate structured patent draft rules from the latest manual/report.

    This remains deterministic: it only detects rules that can be mechanically
    checked. Professional drafting quality is still decided by the Hermes reviewer.
    """
    draft = draft if isinstance(draft, dict) else {}
    description = draft.get("description") or {}
    description = description if isinstance(description, dict) else {}
    title = str(draft.get("title") or draft.get("patent_title") or "").strip()
    abstract = str(draft.get("abstract") or "").strip()
    technical_field = str(description.get("technical_field") or "").strip()
    background = str(description.get("background_art") or "").strip()
    summary = str(description.get("summary_of_invention") or "").strip()
    drawings_description = str(
        description.get("description_of_drawings")
        or description.get("drawings_description")
        or ""
    ).strip()
    detailed = str(description.get("detailed_description") or "").strip()
    full_text = build_patent_text_from_draft(draft)
    issues: List[Dict[str, Any]] = []

    if not title:
        _issue(issues, "critical", "发明名称", "缺少发明名称", "补充清楚、简要且与技术主题一致的发明名称。")
    elif len(title) > 60:
        _issue(issues, "high", "发明名称", f"发明名称超过60字，当前约{len(title)}字", "压缩为能反映主题和类型的名称。")
    elif len(title) > 25:
        _issue(issues, "medium", "发明名称", f"发明名称超过25字，当前约{len(title)}字", "一般应控制在25字以内，必要时不超过60字。")

    claims = draft.get("claims") or {}
    if title and "系统" in title and not _claims_contain_secondary_subject(claims, ("系统",)):
        _issue(
            issues,
            "critical",
            "权利要求书",
            "发明名称包含系统但权利要求书缺少系统独立权利要求",
            "若保护主题为“方法及系统”，必须在权利要求书中增加系统独立权利要求；若只保护方法，则发明名称、摘要和发明内容均应改为方法主题。",
        )
    if title and "装置" in title and not _claims_contain_secondary_subject(claims, ("装置", "设备")):
        _issue(
            issues,
            "critical",
            "权利要求书",
            "发明名称包含装置但权利要求书缺少装置或设备独立权利要求",
            "若保护主题包含装置，必须增加对应装置/设备独立权利要求；若不保护装置，则统一删除题名和正文中的装置主题。",
        )

    if not abstract:
        _issue(issues, "critical", "说明书摘要", "缺少说明书摘要", "摘要必须包含专利名称、技术领域、简化技术方案和技术效果。")
    else:
        if len(abstract) > 300:
            _issue(issues, "high", "说明书摘要", f"摘要超过300字，当前约{len(abstract)}字", "压缩摘要，保留名称、领域、方案和效果。")
        abstract_required_signals = {
            "专利名称": _title_referenced_in_abstract(title, abstract),
            "技术领域": "技术领域" in abstract or "涉及" in abstract,
            "简化技术方案": any(word in abstract for word in ("包括", "首先", "确定", "获取", "处理", "生成")),
            "技术效果": any(word in abstract for word in ("实现", "避免", "提高", "减少", "保证", "保持", "提升")),
        }
        missing = [name for name, passed in abstract_required_signals.items() if not passed]
        if missing:
            _issue(issues, "high", "说明书摘要", f"摘要缺少要素：{'、'.join(missing)}", "按专利名称+技术领域+简化技术方案+技术效果重写摘要。")

    if not technical_field:
        _issue(issues, "critical", "技术领域", "缺少技术领域", "补充具体技术领域。")
    else:
        if len(technical_field) > 120 or "具体地" in technical_field:
            _issue(issues, "high", "技术领域", "技术领域过长或混入具体方案", "技术领域应简明，不写入发明内容或实施方式。")
        if _contains_any(technical_field, ("本发明涉及一种", "尤其涉及一种")) and len(technical_field) > 80:
            _issue(issues, "medium", "技术领域", "技术领域疑似写成发明本身或过度展开", "改为直接所属或直接应用的具体技术领域。")

    if not background:
        _issue(issues, "critical", "背景技术", "缺少背景技术", "背景技术应包含现有技术状况、公开文献或可核验来源及其技术缺陷。")
    else:
        background_paragraphs = [
            part.strip()
            for part in re.split(r"\n{1,}|(?<=[。])\s*(?=第[一二三]段|现有|目前|因此)", background)
            if part.strip()
        ]
        if len(background_paragraphs) < 3:
            _issue(issues, "high", "背景技术", "背景技术未形成三段式结构", "按宏观现有技术、公开文献评述、一个待解决技术问题三段重写。")
        if len(background) > 900:
            _issue(issues, "high", "背景技术", f"背景技术过长，当前约{len(background)}字", "背景技术应精简，避免把实施方式写入背景。")
        if _contains_any(background, ("本发明", "本申请", "本方案")):
            _issue(issues, "high", "背景技术", "背景技术疑似泄露本发明方案或核心发明点", "背景技术只描述现有技术和其缺陷。")
        source_signal = re.search(
            r"(CN\d|CN\s*\d|中国专利|公开号|申请号|公开[日号]|arXiv|DOI|doi|"
            r"https?://|论文|期刊|会议|出版物|公开资料|标准|白皮书)",
            background,
            re.IGNORECASE,
        )
        if not source_signal:
            _issue(
                issues,
                "high",
                "背景技术",
                "背景技术缺少可核验现有技术来源",
                "撰写 Agent 应引用检索 Agent 已确认的真实公开证据；没有专利文献时可引用论文、公开网页或权威网站，并明确其技术方案与不足，禁止虚构专利号。",
                "patent_writer",
            )

    if not summary:
        _issue(issues, "critical", "发明内容", "缺少发明内容", "发明内容必须包含技术问题、技术方案、有益效果。")
    else:
        missing_summary_parts = []
        if "技术问题" not in summary and "解决" not in summary:
            missing_summary_parts.append("技术问题")
        if "技术方案" not in summary and "包括" not in summary:
            missing_summary_parts.append("技术方案")
        effect_signals = (
            "有益效果",
            "实现",
            "避免",
            "提高",
            "减少",
            "保证",
            "保持",
            "提升",
            "降低",
            "增强",
            "改善",
            "从而",
            "能够",
            "通过上述方案",
            "通过上述技术方案",
        )
        if not any(word in summary for word in effect_signals):
            missing_summary_parts.append("有益效果")
        if missing_summary_parts:
            _issue(issues, "high", "发明内容", f"发明内容缺少：{'、'.join(missing_summary_parts)}", "按技术问题、技术方案、有益效果三段式重写。")
        if len(summary) > 1800 or summary.count("具体地") > 2:
            _issue(issues, "medium", "发明内容", "发明内容过度展开", "将实施细节移入具体实施方式，发明内容保持与权利要求对应的概述。")

    if drawings_description:
        figure_numbers = re.findall(r"图\s*([0-9]+)", drawings_description)
        if len(figure_numbers) != len(set(figure_numbers)):
            _issue(issues, "high", "附图说明", "附图说明存在重复图号", "每个图号只能对应一幅图。")
        verbose_lines = [
            line for line in re.split(r"[\n；;。]", drawings_description)
            if len(line.strip()) > 60 and re.search(r"图\s*\d+", line)
        ]
        if verbose_lines:
            _issue(issues, "medium", "附图说明", "附图说明过于冗长", "附图说明应简明写成“图X为……示意图/流程图”。")

    if not detailed:
        _issue(issues, "critical", "具体实施方式", "缺少具体实施方式", "按权利要求步骤和附图充分公开具体实施方式。")
    else:
        if MARKDOWN_HEADING_RE.search(detailed):
            _issue(issues, "high", "具体实施方式", "具体实施方式含 Markdown 标题", "删除 Markdown 标记，改为标准段落。")
        if not re.search(r"S[1-4]", detailed):
            _issue(issues, "high", "具体实施方式", "具体实施方式缺少与独权对应的步骤编号", "按S1-S3或S1-S4逐步展开实施方式。")
        if "可以理解的是" not in detailed or "需要说明的是" not in detailed:
            _issue(issues, "medium", "具体实施方式", "缺少常用解释引导语", "在步骤后加入“可以理解的是”“需要说明的是”解释实现逻辑。")

    return {
        "passed": not any(item["severity"] in {"critical", "high"} for item in issues),
        "issues": issues,
        "metrics": {
            "title_length": len(title),
            "abstract_length": len(abstract),
            "technical_field_length": len(technical_field),
            "background_length": len(background),
            "summary_length": len(summary),
            "detailed_length": len(detailed),
        },
    }


def validate_patent_document_structure(
    patent_document: str,
    drawings: Sequence[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Validate mechanical structural requirements of the whole patent text."""
    text = str(patent_document or "")
    issues: List[Dict[str, Any]] = []

    if TRANSCRIPT_ARTIFACT_RE.search(text):
        issues.append({
            "severity": "critical",
            "location": "全文",
            "issue": "正文残留逐字稿时间戳或说话人格式",
            "suggestion": "回到需求分析/撰写阶段清洗交底内容，只保留技术事实。",
            "target_agent": "patent_writer",
        })
    if MARKDOWN_HEADING_RE.search(text) or "```" in text:
        issues.append({
            "severity": "high",
            "location": "全文",
            "issue": "正文残留 Markdown 标记",
            "suggestion": "删除 Markdown 标题和代码块标记，改为专利文件自然段。",
            "target_agent": "patent_writer",
        })

    duplicate_figs = sorted(set(re.findall(r"图\s*([0-9]+)\s*图\s*\1", text)))
    for fig in duplicate_figs:
        issues.append({
            "severity": "high",
            "location": f"图{fig}",
            "issue": f"图号重复为“图{fig} 图{fig}”",
            "suggestion": "图题只保留一次图号。",
            "target_agent": "patent_writer",
        })

    refs = [f"图{num}" for num in sorted({int(n) for n in FIGURE_REF_RE.findall(text)})]
    drawing_items = list(drawings or [])
    actual = {
        str(item.get("figure_number") or "").replace(" ", "")
        for item in drawing_items
        if isinstance(item, dict)
    }
    if refs and not actual:
        issues.append({
            "severity": "critical",
            "location": "附图",
            "issue": "正文引用附图但未生成对应附图文件",
            "suggestion": "由专利撰写 Agent 调用 patent_drawing_generator 生成附图。",
            "target_agent": "patent_writer",
        })
    if refs and len(drawing_items) < 4:
        issues.append({
            "severity": "high",
            "location": "附图",
            "issue": f"需要附图但附图数量少于4幅，当前{len(drawing_items)}幅",
            "suggestion": "按公司规范规划并生成不少于4幅差异化附图。",
            "target_agent": "patent_writer",
        })
    missing = [ref for ref in refs if ref not in actual]
    for ref in missing:
        issues.append({
            "severity": "critical",
            "location": ref,
            "issue": "正文引用的图号缺少对应附图文件",
            "suggestion": f"补齐{ref}的附图文件并更新附图说明。",
            "target_agent": "patent_writer",
        })

    titles = [
        re.sub(r"^图\s*\d+\s*", "", str(item.get("title") or "")).strip()
        for item in drawing_items
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    if len(titles) != len(set(titles)):
        issues.append({
            "severity": "high",
            "location": "附图",
            "issue": "存在重复附图标题，可能是同一附图内容被重复生成",
            "suggestion": "重新规划每幅图的独立表达目的，避免只换标题。",
            "target_agent": "patent_writer",
        })

    file_hashes: Dict[str, str] = {}
    for item in drawing_items:
        if not isinstance(item, dict):
            continue
        path_text = str(item.get("file_path") or "")
        if not path_text:
            continue
        path = Path(path_text)
        if not path.is_file():
            issues.append({
                "severity": "critical",
                "location": str(item.get("figure_number") or "附图"),
                "issue": "附图文件路径不可访问",
                "suggestion": "重新生成该附图或修正文件路径。",
                "target_agent": "patent_writer",
            })
            continue
        try:
            import hashlib

            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            continue
        fig = str(item.get("figure_number") or "")
        if digest in file_hashes:
            issues.append({
                "severity": "critical",
                "location": "附图",
                "issue": f"{file_hashes[digest]}与{fig}的图片内容完全相同",
                "suggestion": "重新生成差异化附图，每幅图表达不同结构、流程或处理关系。",
                "target_agent": "patent_writer",
            })
            break
        file_hashes[digest] = fig

    return {
        "passed": not any(item["severity"] in {"critical", "high"} for item in issues),
        "issues": issues,
        "metrics": {
            "figure_references": refs,
            "drawing_count": len(drawing_items),
            "has_transcript_artifacts": bool(TRANSCRIPT_ARTIFACT_RE.search(text)),
            "has_markdown": bool(MARKDOWN_HEADING_RE.search(text) or "```" in text),
        },
    }


def build_patent_text_from_draft(draft: Dict[str, Any]) -> str:
    """Flatten a structured draft for deterministic validation."""
    if not isinstance(draft, dict):
        return str(draft or "")
    claims = draft.get("claims") or {}
    description = draft.get("description") or {}
    parts: List[str] = []
    parts.append(str(draft.get("title") or draft.get("patent_title") or ""))
    if isinstance(claims, dict):
        parts.append(str(claims.get("independent_claim") or ""))
        parts.extend(str(item) for item in claims.get("dependent_claims") or [])
    if isinstance(description, dict):
        parts.extend(str(description.get(key) or "") for key in (
            "technical_field",
            "background_art",
            "summary_of_invention",
            "drawings_description",
            "description_of_drawings",
            "detailed_description",
        ))
    parts.append(str(draft.get("abstract") or ""))
    return "\n".join(part for part in parts if part)


def normalize_claims_payload_linebreaks(claims: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of claims with mandatory punctuation line breaks applied."""
    normalized = dict(claims or {})
    if isinstance(normalized.get("independent_claim"), str):
        normalized["independent_claim"] = normalize_claim_linebreaks(normalized["independent_claim"])
    dependent = normalized.get("dependent_claims") or []
    if isinstance(dependent, list):
        normalized["dependent_claims"] = [
            normalize_claim_linebreaks(str(item)) for item in dependent if str(item).strip()
        ]
    elif isinstance(dependent, str):
        normalized["dependent_claims"] = [normalize_claim_linebreaks(dependent)]
    return normalized


def collect_high_priority_issues(*reports: Dict[str, Any]) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()
    for report in reports:
        for issue in report.get("issues", []) if isinstance(report, dict) else []:
            if not isinstance(issue, dict):
                continue
            if issue.get("severity") in {"critical", "high"}:
                location = issue.get("location") or "全文"
                desc = issue.get("issue") or issue.get("description") or ""
                suggestion = issue.get("suggestion") or ""
                key = f"{location}|{desc}|{suggestion}"
                if key in seen:
                    continue
                seen.add(key)
                items.append(f"[{location}] {desc}。建议：{suggestion}")
    return items
