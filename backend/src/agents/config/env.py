"""Environment expansion helpers for Hermes profile YAML."""

from __future__ import annotations

import os
import re
from typing import Any

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any) -> Any:
    """Recursively expand `${VAR}` references in profile configuration."""
    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(lambda match: os.environ.get(match.group(1), match.group(0)), value)
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return value
