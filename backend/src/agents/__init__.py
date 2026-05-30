"""
专利申请多智能体系统 - Agent 层
基于 hermes-agent (run_agent.AIAgent) 架构

配置加载通过 agent_config.py 模块提供，直接使用 hermes-agent 的 AIAgent。
"""

from .agent_config import (
    AgentConfig,
    AgentConfigRegistry,
    get_agent_config_registry,
    get_agent_config,
    create_ai_agent,
)

__all__ = [
    "AgentConfig",
    "AgentConfigRegistry",
    "get_agent_config_registry",
    "get_agent_config",
    "create_ai_agent",
]
