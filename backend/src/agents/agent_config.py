"""Compatibility facade for Hermes agent configuration.

New code should import from `src.agents.config`.  This module remains so older
call sites keep working while the project finishes migrating to the package
layout.
"""

from .config import (
    AgentConfig,
    AgentConfigRegistry,
    HERMES_HOME_DIR,
    HERMES_PROFILES_DIR,
    SYSTEM_CONFIG_DIR,
    create_ai_agent,
    get_agent_config,
    get_agent_config_registry,
)
from .config.env import expand_env as _expand_env
from .config.models import clear_system_defaults_cache, load_system_defaults as _load_system_defaults
from .config.registry import reset_agent_config_registry
from .config.skills import (
    build_profile_skill_prompt as _build_profile_skill_prompt,
    parse_skill_frontmatter as _parse_skill_frontmatter,
)

__all__ = [
    "AgentConfig",
    "AgentConfigRegistry",
    "HERMES_HOME_DIR",
    "HERMES_PROFILES_DIR",
    "SYSTEM_CONFIG_DIR",
    "clear_system_defaults_cache",
    "create_ai_agent",
    "get_agent_config",
    "get_agent_config_registry",
    "reset_agent_config_registry",
]
