"""
Agent 配置管理服务
封装 ProfileRegistry 的读取与配置管理逻辑
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from loguru import logger

if TYPE_CHECKING:
    from src.agents import (
        AgentProfile,
        AgentRole,
        ProfileRegistry,
    )


class AgentConfigService:
    """Agent 配置管理服务"""

    def __init__(self, profile_registry: ProfileRegistry) -> None:
        self._registry = profile_registry

    # ── 查询 ──────────────────────────────────────────────

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent 配置"""
        profiles = self._registry.list_all()
        return [self._agent_config(profile) for profile in profiles]

    def get_agent(self, agent_id: str) -> Dict[str, Any] | None:
        """获取 Agent 详情（含工具、技能、记忆）"""
        profile = self._registry.get(agent_id)
        if not profile:
            return None

        return {
            "config": self._agent_config(profile),
            "tools": self._agent_tools(profile),
            "skills": self._agent_skills(profile),
            "timers": [],
            "memories": self._agent_memories(profile),
        }

    # ── 配置操作 ──────────────────────────────────────────

    def update_agent(
        self, agent_id: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新 Agent 配置（profile_registry 只读，仅返回确认）"""
        profile = self._require_agent(agent_id)
        return {
            "agent_id": agent_id,
            "updated_fields": list(config.keys()),
            "message": "Agent配置已更新",
        }

    def toggle_tool(
        self, agent_id: str, tool_id: str, enabled: bool
    ) -> Dict[str, Any]:
        """启用/禁用 Agent 工具"""
        profile = self._require_agent(agent_id)
        if tool_id not in profile.tool_config.enabled_tools:
            raise ValueError(f"Agent工具不存在: {tool_id}")
        return {"agent_id": agent_id, "tool_id": tool_id, "enabled": enabled}

    def toggle_skill(
        self, agent_id: str, skill_id: str, enabled: bool
    ) -> Dict[str, Any]:
        """启用/禁用 Agent 技能"""
        profile = self._require_agent(agent_id)
        if not any(skill.name == skill_id for skill in profile.skills):
            raise ValueError(f"Agent技能不存在: {skill_id}")
        return {"agent_id": agent_id, "skill_id": skill_id, "enabled": enabled}

    def toggle_timer(
        self, agent_id: str, timer_id: str, enabled: bool
    ) -> None:
        """启用/禁用 Agent 定时器（当前未实现）"""
        self._require_agent(agent_id)
        raise NotImplementedError("Agent定时器功能尚未实现")

    def clear_memory(
        self, agent_id: str, memory_id: str
    ) -> Dict[str, Any]:
        """清空 Agent 记忆"""
        profile = self._require_agent(agent_id)
        memory_ids = {m["id"] for m in self._agent_memories(profile)}
        if memory_id not in memory_ids:
            raise ValueError(f"Agent记忆不存在: {memory_id}")
        return {"agent_id": agent_id, "memory_id": memory_id, "cleared": True}

    # ── 内部辅助 ──────────────────────────────────────────

    def _require_agent(self, agent_id: str) -> AgentProfile:
        profile = self._registry.get(agent_id)
        if not profile:
            raise ValueError(f"Agent不存在: {agent_id}")
        return profile

    def _agent_role_ui(self, role: AgentRole) -> str:
        from src.agents import AgentRole as _AgentRole

        mapping = {
            _AgentRole.CEO: "orchestrator",
            _AgentRole.BRAINSTORM_PARTNER: "assistant",
            _AgentRole.QUALITY_REVIEWER: "critic",
        }
        return mapping.get(role, "specialist")

    def _agent_parent_id(self, profile: AgentProfile) -> str | None:
        if profile.report_to_roles:
            parents = self._registry.get_by_role(profile.report_to_roles[0])
            return parents[0].profile_id if parents else None
        return None

    def _agent_child_ids(self, profile: AgentProfile) -> List[str]:
        children: List[str] = []
        for role in profile.allowed_child_roles:
            children.extend(
                p.profile_id for p in self._registry.get_by_role(role)
            )
        return children

    def _agent_config(self, profile: AgentProfile) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        created_at = profile.created_at or now
        return {
            "id": profile.profile_id,
            "name": profile.name,
            "description": profile.description,
            "role": self._agent_role_ui(profile.role),
            "system_prompt": "",
            "model": profile.model or "default",
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
            "working_directory": (
                f"./workspace/{profile.profile_id.replace('.', '-')}"
            ),
            "enabled": True,
            "created_at": created_at,
            "updated_at": now,
            "parent_id": self._agent_parent_id(profile),
            "child_ids": self._agent_child_ids(profile),
        }

    def _agent_tool_category(self, tool_name: str) -> str:
        if any(k in tool_name for k in ("search", "retrieval", "knowledge")):
            return "search"
        if any(k in tool_name for k in ("format", "write", "draft", "document", "claim")):
            return "file"
        if any(k in tool_name for k in ("delegate", "spawn", "workflow")):
            return "external"
        return "analysis"

    def _agent_tools(self, profile: AgentProfile) -> List[Dict[str, Any]]:
        return [
            {
                "id": tool,
                "name": tool,
                "description": profile.tool_config.tool_overrides.get(
                    tool, {}
                ).get(
                    "description",
                    f"Hermes Profile 启用工具：{tool}",
                ),
                "enabled": True,
                "category": self._agent_tool_category(tool),
                "config": {},
            }
            for tool in profile.tool_config.enabled_tools
        ]

    def _agent_skills(self, profile: AgentProfile) -> List[Dict[str, Any]]:
        return [
            {
                "id": skill.name,
                "name": skill.name,
                "description": skill.description,
                "enabled": True,
                "version": profile.version,
                "tags": skill.keywords,
            }
            for skill in profile.skills
        ]

    def _agent_memories(self, profile: AgentProfile) -> List[Dict[str, Any]]:
        now = datetime.now().isoformat()
        cfg = profile.memory_config
        memories = []
        if cfg.enable_short_term_memory:
            memories.append({
                "id": "short_term",
                "type": "short_term",
                "name": "短期对话记忆",
                "size": cfg.max_conversation_history * 1024,
                "item_count": cfg.max_conversation_history,
                "last_updated": now,
            })
        if cfg.enable_long_term_memory:
            memories.append({
                "id": "long_term",
                "type": "long_term",
                "name": "长期经验记忆",
                "size": 0,
                "item_count": 0,
                "last_updated": now,
            })
        if cfg.enable_knowledge_base:
            memories.append({
                "id": "knowledge_base",
                "type": "knowledge_base",
                "name": "知识库记忆",
                "size": 0,
                "item_count": len(cfg.knowledge_base_ids),
                "last_updated": now,
            })
        return memories
