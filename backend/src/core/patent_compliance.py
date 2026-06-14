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
    # Fallback: count semicolon-separated technical actions after "包括".
    body = text.split("包括", 1)[-1] if "包括" in text else text
    parts = [part.strip() for part in re.split(r"[；;。]\s*", body) if part.strip()]
    return parts


def normalize_claim_linebreaks(claim_text: str) -> str:
    """Force a newline after Chinese/ASCII semicolons and periods in claims."""
    text = str(claim_text or "").strip()
    if not text:
        return ""
    text = re.sub(r"([；;。])\s*", r"\1\n", text)
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

    for idx, block in enumerate(claim_blocks, start=1):
        for match in re.finditer(r"[；;。]", block):
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
    for report in reports:
        for issue in report.get("issues", []) if isinstance(report, dict) else []:
            if not isinstance(issue, dict):
                continue
            if issue.get("severity") in {"critical", "high"}:
                location = issue.get("location") or "全文"
                desc = issue.get("issue") or issue.get("description") or ""
                suggestion = issue.get("suggestion") or ""
                items.append(f"[{location}] {desc}。建议：{suggestion}")
    return items
