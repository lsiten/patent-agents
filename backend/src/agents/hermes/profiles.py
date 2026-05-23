"""
Hermes Agent Profile 系统
定义 Agent 的角色、技能、提示词、工具集、记忆配置等 Profile 属性
支持 Profile 注册、加载、继承与组合
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .base import HermesAgent, HermesTool

from src.core.logging import get_logger

logger = get_logger(__name__)


class AgentRole(str, Enum):
    """Agent 角色枚举 - 专利申请专业分工"""
    CEO = "ceo"                    # CEO - 统筹协调
    REQUIREMENT_ANALYST = "requirement_analyst"   # 需求分析师
    RETRIEVAL_ANALYST = "retrieval_analyst"       # 检索分析师
    PATENT_WRITER = "patent_writer"               # 专利撰写师
    QUALITY_REVIEWER = "quality_reviewer"         # 质量审查师
    BRAINSTORM_PARTNER = "brainstorm_partner"     # 头脑风暴伙伴


class AgentSkill(BaseModel):
    """Agent 技能定义"""
    name: str
    description: str
    proficiency: float = Field(default=0.8, ge=0.0, le=1.0)  # 熟练度
    keywords: List[str] = Field(default_factory=list)       # 关键词匹配


class AgentPromptConfig(BaseModel):
    """Agent 提示词配置"""
    system_prompt: str = ""
    role_description: str = ""
    task_instruction: str = ""
    output_format: str = ""
    few_shot_examples: List[Dict[str, str]] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)

    def build_full_prompt(self) -> str:
        """构建完整的系统提示词"""
        prompt_parts = []

        if self.role_description:
            prompt_parts.append(f"## 角色定位\n{self.role_description}\n")

        if self.task_instruction:
            prompt_parts.append(f"## 任务指令\n{self.task_instruction}\n")

        if self.constraints:
            prompt_parts.append("## 约束条件")
            for constraint in self.constraints:
                prompt_parts.append(f"- {constraint}")
            prompt_parts.append("")

        if self.few_shot_examples:
            prompt_parts.append("## 示例参考")
            for i, example in enumerate(self.few_shot_examples, 1):
                prompt_parts.append(f"\n### 示例 {i}")
                for key, value in example.items():
                    prompt_parts.append(f"**{key}**: {value}")
            prompt_parts.append("")

        if self.output_format:
            prompt_parts.append(f"## 输出格式\n{self.output_format}\n")

        return "\n".join(prompt_parts)


class AgentToolConfig(BaseModel):
    """Agent 工具配置"""
    enabled_tools: List[str] = Field(default_factory=list)  # 启用的工具名称列表
    tool_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)  # 工具参数覆盖
    max_tool_calls_per_turn: int = 5
    enable_parallel_tool_calls: bool = True


class AgentMemoryConfig(BaseModel):
    """Agent 记忆配置"""
    enable_short_term_memory: bool = True
    enable_long_term_memory: bool = False
    max_conversation_history: int = 20
    enable_knowledge_base: bool = False
    knowledge_base_ids: List[str] = Field(default_factory=list)
    memory_retrieval_threshold: float = 0.7


class AgentProfile(BaseModel):
    """
    Hermes Agent Profile - 完整的 Agent 定义
    包含角色、技能、提示词、工具、记忆等所有配置
    """
    profile_id: str
    name: str
    version: str = "1.0.0"
    role: AgentRole

    # 基本描述
    description: str = ""
    author: str = ""
    created_at: str = ""

    # 技能定义
    skills: List[AgentSkill] = Field(default_factory=list)

    # 提示词配置
    prompt_config: AgentPromptConfig = Field(default_factory=AgentPromptConfig)

    # 工具配置
    tool_config: AgentToolConfig = Field(default_factory=AgentToolConfig)

    # 记忆配置
    memory_config: AgentMemoryConfig = Field(default_factory=AgentMemoryConfig)

    # LLM 参数
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    max_iterations: int = 10

    # 协作配置
    can_spawn_agents: bool = False  # 是否可以孵化子 Agent
    allowed_child_roles: List[AgentRole] = Field(default_factory=list)
    report_to_roles: List[AgentRole] = Field(default_factory=list)

    # 元数据
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_system_prompt(self) -> str:
        """获取完整的系统提示词"""
        base_prompt = self.prompt_config.build_full_prompt()

        # 添加技能说明
        if self.skills:
            skill_desc = "## 专业技能\n"
            for skill in self.skills:
                skill_desc += f"- **{skill.name}**: {skill.description}\n"
            base_prompt = skill_desc + "\n" + base_prompt

        # 添加角色标识
        header = f"# {self.name} Agent Profile (v{self.version})\n\n"
        return header + base_prompt

    def has_skill(self, skill_name: str) -> bool:
        """检查是否具备指定技能"""
        return any(skill.name == skill_name for skill in self.skills)

    def get_skill_keywords(self) -> Set[str]:
        """获取所有技能关键词"""
        keywords = set()
        for skill in self.skills:
            keywords.update(skill.keywords)
        return keywords


class ProfileRegistry:
    """
    Agent Profile 注册中心
    管理所有可用的 Agent Profile，支持动态加载与查询
    """

    def __init__(self):
        self._profiles: Dict[str, AgentProfile] = {}
        self._role_to_profiles: Dict[AgentRole, List[str]] = {}
        self._logger = get_logger("profile_registry")

    def register(self, profile: AgentProfile) -> None:
        """注册一个 Agent Profile"""
        if profile.profile_id in self._profiles:
            self._logger.warning(
                "Overwriting existing profile",
                profile_id=profile.profile_id,
            )

        self._profiles[profile.profile_id] = profile

        if profile.role not in self._role_to_profiles:
            self._role_to_profiles[profile.role] = []
        self._role_to_profiles[profile.role].append(profile.profile_id)

        self._logger.info(
            "Registered agent profile",
            profile_id=profile.profile_id,
            role=profile.role.value,
            skills=len(profile.skills),
            tools=len(profile.tool_config.enabled_tools),
        )

    def register_batch(self, profiles: List[AgentProfile]) -> None:
        """批量注册 Profile"""
        for profile in profiles:
            self.register(profile)

    def get(self, profile_id: str) -> Optional[AgentProfile]:
        """获取指定 Profile"""
        return self._profiles.get(profile_id)

    def get_by_role(self, role: AgentRole) -> List[AgentProfile]:
        """按角色获取所有 Profile"""
        profile_ids = self._role_to_profiles.get(role, [])
        return [self._profiles[pid] for pid in profile_ids if pid in self._profiles]

    def list_all(self) -> List[AgentProfile]:
        """列出所有 Profile"""
        return list(self._profiles.values())

    def search(self, query: str) -> List[AgentProfile]:
        """搜索匹配的 Profile（基于关键词和技能）"""
        query_lower = query.lower()
        results = []

        for profile in self._profiles.values():
            # 匹配名称和描述
            if query_lower in profile.name.lower() or query_lower in profile.description.lower():
                results.append(profile)
                continue

            # 匹配技能关键词
            if query_lower in profile.get_skill_keywords():
                results.append(profile)
                continue

            # 匹配标签
            if any(query_lower in tag.lower() for tag in profile.tags):
                results.append(profile)

        return results

    def load_from_json(self, json_path: str) -> None:
        """从 JSON 文件加载 Profile"""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            for item in data:
                profile = AgentProfile.model_validate(item)
                self.register(profile)
        else:
            profile = AgentProfile.model_validate(data)
            self.register(profile)

        self._logger.info("Loaded profiles from file", path=json_path, count=len(self._profiles))


class ProfileBasedAgentFactory:
    """
    基于 Profile 的 Agent 工厂
    根据 Profile 创建和配置 Hermes Agent
    """

    def __init__(self, registry: ProfileRegistry):
        self._registry = registry
        self._tool_registry: Dict[str, Type[HermesTool]] = {}
        self._logger = get_logger("agent_factory")

    def register_tool_class(self, name: str, tool_class: Type[HermesTool]) -> None:
        """注册工具类"""
        self._tool_registry[name] = tool_class

    def create_agent(
        self,
        profile_id: str,
        parent_context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> HermesAgent:
        """
        根据 Profile 创建 Agent

        Args:
            profile_id: Profile ID
            parent_context: 父 Agent 上下文（用于子 Agent 孵化）
            **kwargs: 覆盖 Profile 的参数

        Returns:
            配置好的 Hermes Agent
        """
        profile = self._registry.get(profile_id)
        if not profile:
            raise ValueError(f"Agent profile not found: {profile_id}")

        self._logger.info(
            "Creating agent from profile",
            profile_id=profile_id,
            role=profile.role.value,
        )

        # 合并参数（kwargs 覆盖 Profile 设置）
        model = kwargs.get('model', profile.model)
        temperature = kwargs.get('temperature', profile.temperature)
        max_iterations = kwargs.get('max_iterations', profile.max_iterations)

        # 创建 Agent (lazy import to avoid circular dependency)
        from .base import HermesAgent

        agent = HermesAgent(
            name=profile.name,
            description=profile.description,
            system_prompt=profile.get_system_prompt(),
            model=model,
            temperature=temperature,
            max_iterations=max_iterations,
        )

        # 注册工具
        self._setup_agent_tools(agent, profile, parent_context)

        # 设置元数据
        agent._profile = profile
        agent._parent_context = parent_context

        return agent

    def _setup_agent_tools(
        self,
        agent: HermesAgent,
        profile: AgentProfile,
        parent_context: Optional[Dict[str, Any]],
    ) -> None:
        """配置 Agent 的工具"""
        for tool_name in profile.tool_config.enabled_tools:
            tool_class = self._tool_registry.get(tool_name)
            if tool_class:
                # 获取工具配置覆盖
                tool_kwargs = profile.tool_config.tool_overrides.get(tool_name, {})

                # 如果有父上下文，传递给工具
                if parent_context:
                    tool_kwargs['parent_context'] = parent_context

                # 实例化并注册工具
                try:
                    tool = tool_class(**tool_kwargs)
                    agent.register_tool(tool)
                    self._logger.debug(
                        "Tool registered for agent",
                        agent=agent.name,
                        tool=tool_name,
                    )
                except Exception as e:
                    self._logger.error(
                        "Failed to instantiate tool",
                        tool=tool_name,
                        error=str(e),
                    )
            else:
                self._logger.warning(
                    "Tool class not found in registry",
                    tool=tool_name,
                )

    def create_child_agent(
        self,
        parent_agent: HermesAgent,
        child_profile_id: str,
        task_context: Dict[str, Any],
    ) -> HermesAgent:
        """
        孵化子 Agent（由父 Agent 调用）

        Args:
            parent_agent: 父 Agent
            child_profile_id: 子 Agent 的 Profile ID
            task_context: 任务相关上下文

        Returns:
            子 Agent 实例
        """
        parent_profile = getattr(parent_agent, '_profile', None)

        if parent_profile and not parent_profile.can_spawn_agents:
            raise PermissionError(
                f"Agent {parent_agent.name} does not have permission to spawn child agents"
            )

        self._logger.info(
            "Spawning child agent",
            parent=parent_agent.name,
            child_profile=child_profile_id,
        )

        # 构建子 Agent 上下文
        child_context = {
            'parent_agent_id': parent_agent.context.agent_id,
            'parent_task_context': task_context,
            **(parent_agent._parent_context or {}),
        }

        return self.create_agent(
            profile_id=child_profile_id,
            parent_context=child_context,
        )


# 全局单例
_global_registry: Optional[ProfileRegistry] = None
_global_factory: Optional[ProfileBasedAgentFactory] = None


def get_profile_registry() -> ProfileRegistry:
    """获取全局 Profile 注册中心"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ProfileRegistry()
    return _global_registry


def get_agent_factory() -> ProfileBasedAgentFactory:
    """获取全局 Agent 工厂"""
    global _global_factory
    if _global_factory is None:
        registry = get_profile_registry()
        _global_factory = ProfileBasedAgentFactory(registry)
    return _global_factory
