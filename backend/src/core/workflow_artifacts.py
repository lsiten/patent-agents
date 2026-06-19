# -*- coding: utf-8 -*-
"""Workflow artifact persistence helpers.

The workflow runtime owns orchestration. This module owns the file layout for
phase outputs and graph checkpoints so the engine does not need to carry
filesystem concerns inline.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

PHASE_DIR_MAP = {
    "requirement_analysis": "requirement",
    "retrieval_report": "retrieval",
    "patent_draft": "draft",
    "review_report": "review",
}


def get_task_dir(task_id: str) -> Path:
    """Return the export root for a workflow task."""
    task_dir = BACKEND_DIR / "exports" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def get_phase_dir(task_id: str, phase_field: str) -> Path:
    """Return the export directory for a workflow phase."""
    subdir = PHASE_DIR_MAP.get(phase_field, phase_field)
    phase_dir = get_task_dir(task_id) / subdir
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir


def persist_phase_result(task_id: str, phase_field: str, data: Dict[str, Any]) -> str:
    """Persist a phase result JSON artifact and update latest.json."""
    phase_dir = get_phase_dir(task_id, phase_field)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = phase_dir / f"{phase_field}_{timestamp}.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    file_path.write_text(payload, encoding="utf-8")
    (phase_dir / "latest.json").write_text(payload, encoding="utf-8")
    return str(file_path)


def persist_workflow_checkpoint(task_id: str, checkpoint: Dict[str, Any]) -> str:
    """Persist a LangGraph-style workflow checkpoint snapshot."""
    checkpoint_dir = get_task_dir(task_id) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    reason = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(checkpoint.get("reason") or "checkpoint"))
    file_path = checkpoint_dir / f"{timestamp}_{reason[:80]}.json"
    payload = json.dumps(checkpoint, ensure_ascii=False, indent=2, default=str)
    file_path.write_text(payload, encoding="utf-8")
    (checkpoint_dir / "latest.json").write_text(payload, encoding="utf-8")
    return str(file_path)

