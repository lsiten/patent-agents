"""Hermes agent configuration package.

`backend/hermes_home` stores runtime Hermes profiles and learned skills.
This package is the application adapter that loads those profiles and creates
`run_agent.AIAgent` instances for the patent workflow.
"""

from .factory import create_ai_agent
from .models import AgentConfig
from .paths import HERMES_HOME_DIR, HERMES_PROFILES_DIR, SYSTEM_CONFIG_DIR
from .registry import AgentConfigRegistry, get_agent_config, get_agent_config_registry

__all__ = [
    "AgentConfig",
    "AgentConfigRegistry",
    "HERMES_HOME_DIR",
    "HERMES_PROFILES_DIR",
    "SYSTEM_CONFIG_DIR",
    "create_ai_agent",
    "get_agent_config",
    "get_agent_config_registry",
]
