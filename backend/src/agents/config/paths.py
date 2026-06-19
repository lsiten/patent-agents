"""Filesystem paths for Hermes profile configuration."""

from __future__ import annotations

import os
from pathlib import Path

HERMES_HOME_DIR = Path(__file__).parents[3] / "hermes_home"
HERMES_PROFILES_DIR = HERMES_HOME_DIR / "profiles"
SYSTEM_CONFIG_DIR = HERMES_PROFILES_DIR / "system-config"


def ensure_hermes_home() -> None:
    """Ensure the Hermes home exists and expose it for hermes-agent."""
    HERMES_HOME_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HERMES_HOME", str(HERMES_HOME_DIR))


ensure_hermes_home()
