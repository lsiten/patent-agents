"""
Hermes Agent 框架 - 基于 NousResearch Hermes Agent 架构

提供完整的 Agent 运行时能力:
- 思考-行动 (ReAct) 循环
- 函数调用与工具集成
- 结构化输出 (JSON Schema)
- 子 Agent 孵化
- 多 Agent 协调 (CEO 模式)
- 记忆系统 (短期/长期/知识库)
"""

from .base import (
    HermesAgent,
    HermesAgentContext,
    HermesAgentCoordinator,
    HermesFunctionCall,
    HermesFunctionResult,
    HermesMessage,
    HermesMessageRole,
    HermesTool,
    HermesToolDefinition,
    HermesToolParameter,
)

from .memory import (
    MemoryItem,
    MemoryStore,
    InMemoryStore,
    ShortTermMemory,
    LongTermMemory,
    KnowledgeBase,
    AgentMemoryManager,
)

from .profiles import (
    AgentProfile,
    AgentRole,
    AgentSkill,
    AgentPromptConfig,
    AgentToolConfig,
    AgentMemoryConfig,
    ProfileRegistry,
    ProfileBasedAgentFactory,
    get_profile_registry,
    get_agent_factory,
)

__all__ = [
    # Hermes 核心类
    "HermesAgent",
    "HermesAgentContext",
    "HermesAgentCoordinator",
    "HermesFunctionCall",
    "HermesFunctionResult",
    "HermesMessage",
    "HermesMessageRole",
    "HermesTool",
    "HermesToolDefinition",
    "HermesToolParameter",
    # 记忆系统
    "MemoryItem",
    "MemoryStore",
    "InMemoryStore",
    "ShortTermMemory",
    "LongTermMemory",
    "KnowledgeBase",
    "AgentMemoryManager",
    # Profile 系统
    "AgentProfile",
    "AgentRole",
    "AgentSkill",
    "AgentPromptConfig",
    "AgentToolConfig",
    "AgentMemoryConfig",
    "ProfileRegistry",
    "ProfileBasedAgentFactory",
    "get_profile_registry",
    "get_agent_factory",
]
