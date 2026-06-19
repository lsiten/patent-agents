"""Hermes profile skill loading and prompt assembly."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


def parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from a `SKILL.md` file."""
    if not content.startswith("---"):
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def load_profile_skills(profile_dir: Path) -> List[Dict[str, Any]]:
    """Load all enabled skill metadata and content from one Hermes profile."""
    skills_dir = profile_dir / "skills"
    if not skills_dir.exists():
        return []

    result: List[Dict[str, Any]] = []
    for skill_subdir in skills_dir.iterdir():
        if not skill_subdir.is_dir():
            continue

        skill_file = skill_subdir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            meta = parse_skill_frontmatter(content)
            result.append(
                {
                    "name": meta.get("name", skill_subdir.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "1.0.0"),
                    "file": f"{skill_subdir.name}/SKILL.md",
                    "enabled": meta.get("enabled", True),
                    "tags": meta.get("metadata", {}).get("tags", []),
                    "content": content,
                }
            )
        except Exception as exc:
            logger.warning("Failed to load skill %s: %s", skill_subdir.name, exc)

    return result


def build_profile_skill_prompt(
    skills: List[Dict[str, Any]],
    max_chars_per_skill: int = 2400,
) -> str:
    """Build a compact Hermes-compatible skill context for the current profile."""
    enabled_skills = [skill for skill in skills if skill.get("enabled", True)]
    if not enabled_skills:
        return ""

    parts = [
        "# Hermes Profile Skills",
        "",
        "以下是当前 Agent 自己 profile 下的 Hermes SKILL.md 技能资产。执行任务时优先复用这些过程经验；"
        "如果技能与当前任务无关，可以忽略。",
    ]
    for skill in enabled_skills:
        name = str(skill.get("name") or "unnamed-skill")
        description = str(skill.get("description") or "")
        content = str(skill.get("content") or "").strip()
        if len(content) > max_chars_per_skill:
            content = content[:max_chars_per_skill].rstrip() + "\n\n[技能内容已截断，请优先遵守以上可见部分。]"
        parts.append(f"\n## Skill: {name}")
        if description:
            parts.append(f"Description: {description}")
        parts.append(content)
    return "\n".join(parts).strip()
