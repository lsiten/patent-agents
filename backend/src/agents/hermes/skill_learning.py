# -*- coding: utf-8 -*-
"""Hermes-compatible automatic skill sedimentation.

Hermes agents already understand skills as procedural memory stored under
``$HERMES_HOME/skills/<skill>/SKILL.md``.  This module writes learned, role-local
skills into each project profile so every agent grows its own reusable capability
from finished patent workflows.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


_BACKEND_DIR = Path(__file__).resolve().parents[3]
_PROFILES_DIR = _BACKEND_DIR / "hermes_home" / "profiles"

_MAX_LOG_RECORDS = 30


AGENT_SKILL_TARGETS: Dict[str, Dict[str, str]] = {
    "ceo": {
        "skill": "auto-agent-loop-orchestration",
        "name": "auto-agent-loop-orchestration",
        "description": "自动沉淀的专利 Agent Loop 调度、反馈闭环和终止条件经验",
    },
    "requirement_analyst": {
        "skill": "auto-requirement-analysis-lessons",
        "name": "auto-requirement-analysis-lessons",
        "description": "自动沉淀的交底/沟通内容清洗、主题识别和需求结构化经验",
    },
    "retrieval_analyst": {
        "skill": "auto-retrieval-analysis-lessons",
        "name": "auto-retrieval-analysis-lessons",
        "description": "自动沉淀的专利检索关键词、检索策略和对比分析经验",
    },
    "patent_writer": {
        "skill": "auto-patent-writing-lessons",
        "name": "auto-patent-writing-lessons",
        "description": "自动沉淀的专利分步撰写、附图生成和 DOCX 写入经验",
    },
    "quality_reviewer": {
        "skill": "auto-quality-review-lessons",
        "name": "auto-quality-review-lessons",
        "description": "自动沉淀的专利质量审查、附图审查和复审闭环经验",
    },
}


def _safe_text(value: Any, max_len: int = 360) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _load_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    safe_records: List[Dict[str, Any]] = []
    forbidden_keys = {
        "task_id",
        "title",
        "technical_problem",
        "innovation_points",
        "strategy",
        "final_document_path",
        "drawing_titles",
        "review_issues",
    }
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("record_type") != "abstract_workflow_lesson":
            continue
        if any(key in item for key in forbidden_keys):
            continue
        safe_records.append(item)
    return safe_records


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _review_issues(snapshot: Dict[str, Any]) -> List[str]:
    feedback = _as_dict(snapshot.get("feedback"))
    issues = [_safe_text(item, 220) for item in _as_list(feedback.get("review_issues"))]
    return [item for item in issues if item][:8]


def _issue_categories(issues: Iterable[str]) -> List[str]:
    categories: List[str] = []
    mapping = [
        (("标题", "发明名称"), "标题需清楚、简要且与技术主题一致"),
        (("摘要",), "摘要需包含专利名称、技术领域、简化方案和技术效果"),
        (("权利要求", "独立权利要求", "从属"), "权利要求需短句分行、独权3或4步、从权逐项限定"),
        (("说明书", "实施方式", "公开"), "说明书需充分公开可实施细节并避免Markdown和交底噪声"),
        (("附图", "图号", "图片"), "附图需按当前专利内容逐图差异化生成并插入DOCX"),
        (("DOCX", "下载", "文件"), "最终DOCX路径、图片资源和下载可用性必须确认"),
        (("检索", "现有技术", "创造性"), "检索报告需支撑区别特征和创造性论证"),
    ]
    joined_issues = "；".join(str(item) for item in issues)
    for keywords, category in mapping:
        if any(keyword in joined_issues for keyword in keywords) and category not in categories:
            categories.append(category)
    return categories[:8]


def _last_phase_status(snapshot: Dict[str, Any], phase_name: str) -> str:
    history = _as_list(snapshot.get("phase_history"))
    matched = [
        item for item in history
        if isinstance(item, dict) and str(item.get("phase", "")).lower() == phase_name
    ]
    if not matched:
        return "unknown"
    return "success" if matched[-1].get("success") else "needs_attention"


def _build_record(agent_profile: str, context: Any, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    draft = _as_dict(getattr(context, "patent_draft", {}))
    requirements = _as_dict(getattr(context, "requirement_analysis", {}))
    retrieval = _as_dict(getattr(context, "retrieval_report", {}))
    feedback = _as_dict(snapshot.get("feedback"))

    review_issues = _review_issues(snapshot)
    base = {
        "record_type": "abstract_workflow_lesson",
        "terminal_state": snapshot.get("terminal_state", ""),
        "generated_at": datetime.now().isoformat(),
        "iteration_count": _as_dict(snapshot.get("context")).get("iteration_count", 0),
        "review_recommendation": _safe_text(feedback.get("review_recommendation"), 80),
        "review_issue_categories": _issue_categories(review_issues),
    }

    if agent_profile == "ceo":
        base.update({
            "learned_focus": "调度顺序、质量反馈闭环、终止条件与人工等待状态",
            "loop_topology": _as_dict(snapshot.get("policy")).get("topology", []),
            "quality_remediation_required": bool(feedback.get("quality_remediation")),
        })
    elif agent_profile == "requirement_analyst":
        base.update({
            "learned_focus": "从逐字稿/沟通材料提炼技术主题，剔除口语化、时间戳和格式噪声",
            "phase_status": _last_phase_status(snapshot, "requirement"),
            "has_innovation_points": bool(_as_list(requirements.get("innovation_points"))),
            "has_technical_problem": bool(_safe_text(requirements.get("technical_problem"), 260)),
        })
    elif agent_profile == "retrieval_analyst":
        strategy = retrieval.get("retrieval_strategy") or retrieval.get("search_strategy") or {}
        base.update({
            "learned_focus": "围绕技术主题构造关键词、同义词和检索式，沉淀先有技术对比角度",
            "phase_status": _last_phase_status(snapshot, "retrieval"),
            "has_search_strategy": bool(strategy),
            "key_references_count": len(_as_list(retrieval.get("key_references") or retrieval.get("references"))),
        })
    elif agent_profile == "patent_writer":
        drawings = _as_list(draft.get("drawings"))
        base.update({
            "learned_focus": "按章节分步撰写，附图逐图差异化生成，并在 DOCX 对应位置插入",
            "phase_status": _last_phase_status(snapshot, "writing"),
            "has_drawings": bool(drawings),
            "drawing_count": len(drawings),
            "has_final_document": bool(_as_dict(snapshot.get("context")).get("final_document_path", "")),
        })
    elif agent_profile == "quality_reviewer":
        base.update({
            "learned_focus": "同时审查文本、权利要求、说明书一致性、附图缺失/重复和 DOCX 可用性",
            "phase_status": _last_phase_status(snapshot, "review"),
            "checked_drawings": _as_dict(_as_dict(getattr(context, "review_report", {})).get("drawing_review")).get("checked_drawings"),
        })

    return base


def _dedupe_append(records: List[Dict[str, Any]], record: Dict[str, Any]) -> List[Dict[str, Any]]:
    records.append(record)
    return records[-_MAX_LOG_RECORDS:]


def _render_examples(records: Iterable[Dict[str, Any]]) -> str:
    categories: List[str] = []
    for item in records:
        for category in item.get("review_issue_categories") or []:
            if category not in categories:
                categories.append(category)
    if not categories:
        return "- 本轮未沉淀可复用缺陷类型。"
    return "\n".join(f"- {category}" for category in categories[:8])


def _render_skill(agent_profile: str, target: Dict[str, str], records: List[Dict[str, Any]]) -> str:
    latest = records[-1] if records else {}
    focus = _safe_text(latest.get("learned_focus"), 240)
    examples = _render_examples(records)

    role_guidance = {
        "ceo": [
            "每次进入专利流程前，先明确 Done：质量审查可接受、关键问题清零、最终 DOCX 存在。",
            "质量审查给出 revise/reject 或低分时，不结束流程；把具体问题传回对应 Agent 修复后再复审。",
            "连续无进展或缺少用户信息时进入等待状态，并保留失败反馈供恢复后继续。",
        ],
        "requirement_analyst": [
            "逐字稿、聊天记录和交底材料只作为事实来源，不把时间戳、说话人、寒暄和格式噪声写入专利文本。",
            "先提炼专利主题、技术问题、核心创新点、关键实施细节，再交给检索和撰写阶段。",
            "信息不足时输出明确缺口，便于 CEO 调度头脑风暴或向用户追问。",
        ],
        "retrieval_analyst": [
            "围绕主题拆分核心关键词、同义词、功能效果词和应用场景词，记录检索式与数据库来源。",
            "检索报告要服务撰写：指出区别特征、可规避风险和需要强化的创新点。",
            "检索过程和中间结果需要可展示，避免只给最终结论。",
        ],
        "patent_writer": [
            "长文档必须分章节、分轮次写入草稿和 DOCX，避免一次性输出超上下文。",
            "附图不能复用同一图改标题；每张图要有独立结构、独立说明和唯一图号。",
            "生成 DOCX 前检查摘要、权利要求、说明书、附图说明和实际插图位置一致。",
        ],
        "quality_reviewer": [
            "审查不只看文本合规，还要检查附图是否缺失、重复、图号重复、说明与正文是否一致。",
            "发现问题时输出可调度的缺陷清单：归属 Agent、严重级别、修复建议和复审条件。",
            "只有关键问题可接受且最终 DOCX 可下载时才允许通过。",
        ],
    }
    guidance = "\n".join(f"- {line}" for line in role_guidance.get(agent_profile, []))

    return f"""---
name: {target["name"]}
description: {target["description"]}
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: {agent_profile}
---

# {target["description"]}

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

{focus or "结合最近专利流程结果，复用可执行的阶段经验和质量反馈。"}

## 执行准则

{guidance}

## 可复用缺陷类型

{examples}

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略；禁止写入任务 ID、历史标题、历史附图标题、完整交底原文或用户隐私内容。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
"""


def sediment_workflow_skills(context: Any, loop_snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    """Write per-agent learned skills and return the touched files."""
    touched: List[Dict[str, str]] = []
    for agent_profile, target in AGENT_SKILL_TARGETS.items():
        profile_dir = _PROFILES_DIR / agent_profile
        if not profile_dir.exists():
            continue

        skill_dir = profile_dir / "skills" / target["skill"]
        references_dir = skill_dir / "references"
        log_path = references_dir / "learning-log.json"
        skill_path = skill_dir / "SKILL.md"

        records = _load_records(log_path)
        record = _build_record(agent_profile, context, loop_snapshot)
        records = _dedupe_append(records, record)
        _write_json(log_path, records)
        _write_text(skill_path, _render_skill(agent_profile, target, records))
        touched.append({
            "agent_profile": agent_profile,
            "skill": target["skill"],
            "skill_path": str(skill_path),
            "log_path": str(log_path),
        })
    return touched
