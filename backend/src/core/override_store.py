"""
Agent Override Store — 持久化 Agent 配置覆盖层
存储用户通过前端对 Agent Profile 的修改（启用/禁用工具、添加工具/技能/定时器、修改参数等）
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)

OVERRIDES_FILE = Path(__file__).parent.parent / "data" / "agent_overrides.json"


class AgentOverrideStore:
    """
    Agent 配置覆盖存储
    Profile 提供默认值，本 store 存储用户修改的覆盖值
    最终配置 = Profile 默认 + Override
    """

    def __init__(self):
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """从文件加载覆盖配置"""
        if not OVERRIDES_FILE.exists():
            logger.info("No overrides file, starting fresh")
            return
        try:
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                self._overrides = json.load(f)
            logger.info("Loaded agent overrides", count=len(self._overrides))
        except Exception as e:
            logger.error("Failed to load overrides", error=str(e))
            self._overrides = {}

    def save(self) -> None:
        """持久化覆盖配置"""
        OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(self._overrides, f, ensure_ascii=False, indent=2)

    def _ensure_agent(self, agent_id: str) -> Dict[str, Any]:
        """确保 agent 条目存在"""
        if agent_id not in self._overrides:
            self._overrides[agent_id] = {
                "config_overrides": {},
                "tools_disabled": [],
                "tools_added": [],
                "skills_disabled": [],
                "skills_added": [],
                "timers": [],
            }
        return self._overrides[agent_id]

    # ============ Config Overrides ============

    def get_config_overrides(self, agent_id: str) -> Dict[str, Any]:
        """获取 Agent 配置覆盖"""
        entry = self._overrides.get(agent_id, {})
        return entry.get("config_overrides", {})

    def update_config(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """更新 Agent 配置"""
        entry = self._ensure_agent(agent_id)
        entry["config_overrides"].update(updates)
        self.save()

    # ============ Tool Overrides ============

    def is_tool_disabled(self, agent_id: str, tool_name: str) -> bool:
        """检查工具是否被禁用"""
        entry = self._overrides.get(agent_id, {})
        return tool_name in entry.get("tools_disabled", [])

    def toggle_tool(self, agent_id: str, tool_name: str, enabled: bool) -> None:
        """切换工具启用状态"""
        entry = self._ensure_agent(agent_id)
        disabled_list = entry.setdefault("tools_disabled", [])
        if enabled and tool_name in disabled_list:
            disabled_list.remove(tool_name)
        elif not enabled and tool_name not in disabled_list:
            disabled_list.append(tool_name)
        self.save()

    def get_added_tools(self, agent_id: str) -> List[Dict[str, Any]]:
        """获取用户添加的工具"""
        entry = self._overrides.get(agent_id, {})
        return entry.get("tools_added", [])

    def add_tool(self, agent_id: str, tool_data: Dict[str, Any]) -> None:
        """添加新工具"""
        entry = self._ensure_agent(agent_id)
        entry.setdefault("tools_added", []).append(tool_data)
        self.save()

    def update_tool(self, agent_id: str, tool_id: str, updates: Dict[str, Any]) -> bool:
        """更新已添加的工具"""
        entry = self._ensure_agent(agent_id)
        for tool in entry.get("tools_added", []):
            if tool.get("id") == tool_id:
                tool.update(updates)
                self.save()
                return True
        return False

    def delete_tool(self, agent_id: str, tool_id: str) -> bool:
        """删除已添加的工具"""
        entry = self._ensure_agent(agent_id)
        tools = entry.get("tools_added", [])
        original_len = len(tools)
        entry["tools_added"] = [t for t in tools if t.get("id") != tool_id]
        if len(entry["tools_added"]) < original_len:
            self.save()
            return True
        return False

    # ============ Skill Overrides ============

    def is_skill_disabled(self, agent_id: str, skill_name: str) -> bool:
        """检查技能是否被禁用"""
        entry = self._overrides.get(agent_id, {})
        return skill_name in entry.get("skills_disabled", [])

    def toggle_skill(self, agent_id: str, skill_name: str, enabled: bool) -> None:
        """切换技能启用状态"""
        entry = self._ensure_agent(agent_id)
        disabled_list = entry.setdefault("skills_disabled", [])
        if enabled and skill_name in disabled_list:
            disabled_list.remove(skill_name)
        elif not enabled and skill_name not in disabled_list:
            disabled_list.append(skill_name)
        self.save()

    def get_added_skills(self, agent_id: str) -> List[Dict[str, Any]]:
        """获取用户添加的技能"""
        entry = self._overrides.get(agent_id, {})
        return entry.get("skills_added", [])

    def add_skill(self, agent_id: str, skill_data: Dict[str, Any]) -> None:
        """添加新技能"""
        entry = self._ensure_agent(agent_id)
        entry.setdefault("skills_added", []).append(skill_data)
        self.save()

    def update_skill(self, agent_id: str, skill_id: str, updates: Dict[str, Any]) -> bool:
        """更新已添加的技能"""
        entry = self._ensure_agent(agent_id)
        for skill in entry.get("skills_added", []):
            if skill.get("id") == skill_id:
                skill.update(updates)
                self.save()
                return True
        return False

    def delete_skill(self, agent_id: str, skill_id: str) -> bool:
        """删除已添加的技能"""
        entry = self._ensure_agent(agent_id)
        skills = entry.get("skills_added", [])
        original_len = len(skills)
        entry["skills_added"] = [s for s in skills if s.get("id") != skill_id]
        if len(entry["skills_added"]) < original_len:
            self.save()
            return True
        return False

    # ============ LLM / ImageGen Overrides (per-agent 加密覆盖) ============

    _LLM_OVERRIDE_KEY = "llm_override"
    _IMAGE_GEN_OVERRIDE_KEY = "image_gen_override"

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """暴露原始 entry dict，方便测试和内部使用"""
        return self._overrides.get(agent_id, {})

    def get_llm_override(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取 agent 的 LLM 运行时覆盖（已解密 api_key）。未设置返回 None。"""
        from .secret_cipher import decrypt_value

        entry = self._overrides.get(agent_id, {})
        raw = entry.get(self._LLM_OVERRIDE_KEY)
        if not raw:
            return None
        result = dict(raw)
        if "api_key" in result and result["api_key"]:
            result["api_key"] = decrypt_value(result["api_key"])
        return result

    def update_llm_override(self, agent_id: str, llm_config: Dict[str, Any]) -> None:
        """
        更新 agent 的 LLM 运行时覆盖。api_key 加密后存盘。
        其他字段（provider / base_url / model）明文存。
        """
        from .secret_cipher import encrypt_value

        entry = self._ensure_agent(agent_id)
        stored = dict(llm_config)
        if stored.get("api_key"):
            stored["api_key"] = encrypt_value(stored["api_key"])
        entry[self._LLM_OVERRIDE_KEY] = stored
        self.save()

    def clear_llm_override(self, agent_id: str) -> None:
        """清除 agent 的 LLM 覆盖（回到 yaml / system-config / 全局）"""
        entry = self._overrides.get(agent_id)
        if not entry or self._LLM_OVERRIDE_KEY not in entry:
            return
        del entry[self._LLM_OVERRIDE_KEY]
        self.save()

    def get_image_gen_override(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取 agent 的生图运行时覆盖（已解密 api_key）。未设置返回 None。"""
        from .secret_cipher import decrypt_value

        entry = self._overrides.get(agent_id, {})
        raw = entry.get(self._IMAGE_GEN_OVERRIDE_KEY)
        if not raw:
            return None
        result = dict(raw)
        if "api_key" in result and result["api_key"]:
            result["api_key"] = decrypt_value(result["api_key"])
        return result

    def update_image_gen_override(self, agent_id: str, img_config: Dict[str, Any]) -> None:
        """更新 agent 的生图运行时覆盖。api_key 加密后存盘。"""
        from .secret_cipher import encrypt_value

        entry = self._ensure_agent(agent_id)
        stored = dict(img_config)
        if stored.get("api_key"):
            stored["api_key"] = encrypt_value(stored["api_key"])
        entry[self._IMAGE_GEN_OVERRIDE_KEY] = stored
        self.save()

    def clear_image_gen_override(self, agent_id: str) -> None:
        """清除 agent 的生图覆盖"""
        entry = self._overrides.get(agent_id)
        if not entry or self._IMAGE_GEN_OVERRIDE_KEY not in entry:
            return
        del entry[self._IMAGE_GEN_OVERRIDE_KEY]
        self.save()

    # ============ Timer Overrides ============

    def get_timers(self, agent_id: str) -> List[Dict[str, Any]]:
        """获取 Agent 的所有定时器"""
        entry = self._overrides.get(agent_id, {})
        return entry.get("timers", [])

    def add_timer(self, agent_id: str, timer_data: Dict[str, Any]) -> None:
        """添加定时器"""
        entry = self._ensure_agent(agent_id)
        entry.setdefault("timers", []).append(timer_data)
        self.save()

    def update_timer(self, agent_id: str, timer_id: str, updates: Dict[str, Any]) -> bool:
        """更新定时器"""
        entry = self._ensure_agent(agent_id)
        for timer in entry.get("timers", []):
            if timer.get("id") == timer_id:
                timer.update(updates)
                self.save()
                return True
        return False

    def toggle_timer(self, agent_id: str, timer_id: str, enabled: bool) -> bool:
        """切换定时器启用状态"""
        return self.update_timer(agent_id, timer_id, {"enabled": enabled})

    def delete_timer(self, agent_id: str, timer_id: str) -> bool:
        """删除定时器"""
        entry = self._ensure_agent(agent_id)
        timers = entry.get("timers", [])
        original_len = len(timers)
        entry["timers"] = [t for t in timers if t.get("id") != timer_id]
        if len(entry["timers"]) < original_len:
            self.save()
            return True
        return False


# 全局单例
_store: Optional[AgentOverrideStore] = None


def get_override_store() -> AgentOverrideStore:
    """获取全局覆盖存储实例"""
    global _store
    if _store is None:
        _store = AgentOverrideStore()
    return _store
