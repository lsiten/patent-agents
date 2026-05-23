"""
专利申请多智能体系统 - Agent 层
基于 NousResearch Hermes Agent 架构
"""

from .hermes import (
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
    # 记忆系统
    MemoryItem,
    MemoryStore,
    InMemoryStore,
    ShortTermMemory,
    LongTermMemory,
    KnowledgeBase,
    AgentMemoryManager,
    # Profile 系统
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

from .profiles.default_profiles import (
    register_default_profiles,
    create_ceo_agent_profile,
    create_requirement_analyst_profile,
    create_retrieval_analyst_profile,
    create_patent_writer_profile,
    create_quality_reviewer_profile,
    create_brainstorm_partner_profile,
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
    # 默认 Profiles
    "register_default_profiles",
    "create_ceo_agent_profile",
    "create_requirement_analyst_profile",
    "create_retrieval_analyst_profile",
    "create_patent_writer_profile",
    "create_quality_reviewer_profile",
    "create_brainstorm_partner_profile",
]
