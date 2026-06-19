"""Hermes profile configuration models."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import paths
from .env import expand_env
from .skills import load_profile_skills

logger = logging.getLogger(__name__)

_system_defaults: Optional[Dict[str, Any]] = None


def clear_system_defaults_cache() -> None:
    """Clear cached system defaults, mainly for tests and config reloads."""
    global _system_defaults
    _system_defaults = None


def load_system_defaults() -> Dict[str, Any]:
    """Load `system-config` as global default profile settings."""
    global _system_defaults
    if _system_defaults is not None:
        return _system_defaults

    config_path = paths.SYSTEM_CONFIG_DIR / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                raw = yaml.safe_load(file) or {}
            _system_defaults = expand_env(raw)
            logger.info("Loaded system defaults from %s", config_path)
        except Exception as exc:
            logger.warning("Failed to load system defaults: %s", exc)
            _system_defaults = {}
    else:
        logger.warning("System config not found: %s", config_path)
        _system_defaults = {}

    return _system_defaults


class AgentConfig:
    """Single Hermes profile config with system-config fallback."""

    def __init__(self, dir_path: Path):
        self.dir_path = dir_path
        self._config: Dict[str, Any] = {}
        self._soul_md: str = ""
        self._defaults: Dict[str, Any] = load_system_defaults()
        self._load()

    def _load(self) -> None:
        config_path = self.dir_path / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as file:
                raw = yaml.safe_load(file) or {}
            self._config = expand_env(raw)

        soul_path = self.dir_path / "SOUL.md"
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as file:
                self._soul_md = file.read()

    def _get(self, key: str, default_value: Any = None) -> Any:
        if key in self._config:
            return self._config[key]
        if key in self._defaults:
            return self._defaults[key]
        return default_value

    @property
    def profile_id(self) -> str:
        return self._get("profile_id", self.dir_path.name)

    @property
    def name(self) -> str:
        return self._get("name", self.profile_id)

    @property
    def description(self) -> str:
        return self._get("description", "")

    @property
    def role(self) -> str:
        return self._get("role", "specialist")

    @property
    def model(self) -> str:
        return self._get("model", "default")

    @property
    def temperature(self) -> float:
        return self._get("temperature", 0.7)

    @property
    def max_tokens(self) -> int:
        return self._get("max_tokens", 4096)

    @property
    def max_iterations(self) -> int:
        return self._get("max_iterations", 20)

    @property
    def enabled_tools(self) -> List[str]:
        return self._get("enabled_tools", [])

    @property
    def enabled_toolsets(self) -> List[str]:
        return self._get("enabled_toolsets", ["patent"])

    @property
    def api_mode(self) -> Optional[str]:
        return self._get("api_mode")

    @property
    def llm(self) -> Dict[str, Any]:
        val = self._config.get("llm")
        if val:
            return val
        default = self._defaults.get("llm")
        if default:
            return default
        return {}

    @property
    def image_gen(self) -> Dict[str, Any]:
        val = self._config.get("image_gen")
        if val:
            return val
        default = self._defaults.get("image_gen")
        if default:
            return default
        return {}

    @property
    def soul_md(self) -> str:
        return self._soul_md

    @property
    def raw_config(self) -> Dict[str, Any]:
        return self._config.copy()

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def skills(self) -> List[Dict[str, Any]]:
        return load_profile_skills(self.dir_path)
