"""Deterministic patent document rule constants."""

from __future__ import annotations

INDEPENDENT_CLAIM_ALLOWED_STEP_COUNTS = (3, 4)
INDEPENDENT_CLAIM_MAX_CHARS = 250
DEPENDENT_CLAIM_MAX_CHARS = 200

PATENT_REQUIRED_SECTIONS = (
    "说明书摘要",
    "摘要附图",
    "权利要求书",
    "说明书",
    "技术领域",
    "背景技术",
    "发明内容",
    "附图说明",
    "具体实施方式",
    "说明书附图",
)

TRANSCRIPT_ARTIFACT_MARKERS = (
    "逐字稿",
    "会议记录",
    "转写文本",
)

