"""Hermes profile registry."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from . import paths
from .models import AgentConfig

logger = logging.getLogger(__name__)


class AgentConfigRegistry:
    """Load and expose all Hermes profile configurations."""

    def __init__(self):
        self._configs: Dict[str, AgentConfig] = {}
        self._patent_tools_registered = False
        self._load_all()

    def _load_all(self) -> None:
        if not paths.HERMES_PROFILES_DIR.exists():
            logger.warning("Profiles directory not found: %s", paths.HERMES_PROFILES_DIR)
            return

        for subdir in paths.HERMES_PROFILES_DIR.iterdir():
            if subdir.name == "system-config":
                continue
            if subdir.is_dir() and (subdir / "config.yaml").exists():
                try:
                    config = AgentConfig(subdir)
                    self._configs[config.profile_id] = config
                    logger.info("Loaded agent config: %s (%s)", config.name, config.profile_id)
                except Exception as exc:
                    logger.error("Failed to load config from %s: %s", subdir, exc)

    def ensure_patent_tools(self) -> None:
        """Register project patent tools in hermes-agent once."""
        if self._patent_tools_registered:
            return
        try:
            from src.agents.hermes.tools.adapter import init_patent_tools

            init_patent_tools()
            self._patent_tools_registered = True
            logger.info("Patent tools registered to hermes-agent")
        except Exception as exc:
            logger.error("Failed to register patent tools: %s", exc)

    def get(self, profile_id: str) -> Optional[AgentConfig]:
        return self._configs.get(profile_id)

    def get_all(self) -> List[AgentConfig]:
        return list(self._configs.values())

    def list_ids(self) -> List[str]:
        return list(self._configs.keys())


_registry: Optional[AgentConfigRegistry] = None


def reset_agent_config_registry() -> None:
    """Reset the singleton registry, mainly for tests and config reloads."""
    global _registry
    _registry = None


def get_agent_config_registry() -> AgentConfigRegistry:
    global _registry
    if _registry is None:
        _registry = AgentConfigRegistry()
    return _registry


def get_agent_config(profile_id: str) -> Optional[AgentConfig]:
    return get_agent_config_registry().get(profile_id)
