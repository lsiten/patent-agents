"""
Tests for per-agent LLM/image_gen config in AgentConfig:
1. ${ENV_VAR} 引用递归展开
2. llm / image_gen 子段从 agent config 读取，缺失时回退 system-config
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_profile_dirs(tmp_path, monkeypatch):
    """
    构造临时 profiles 目录结构：
        tmp_path/
          profiles/
            system-config/config.yaml
            my_agent/config.yaml
    并 monkeypatch HERMES_PROFILES_DIR 到 tmp_path/profiles。
    """
    profiles = tmp_path / "profiles"
    (profiles / "system-config").mkdir(parents=True)
    (profiles / "my_agent").mkdir(parents=True)

    # 重置 _load_system_defaults 的全局缓存
    from src.agents import agent_config as ac
    ac._system_defaults = None

    monkeypatch.setattr(ac, "HERMES_PROFILES_DIR", profiles)
    monkeypatch.setattr(ac, "SYSTEM_CONFIG_DIR", profiles / "system-config")
    yield profiles

    ac._system_defaults = None


def write_yaml(path: Path, data: dict) -> None:
    import yaml
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


# ── 1) ${ENV_VAR} 展开 ──────────────────────────────────────────────


class TestEnvExpansion:
    def test_string_value_with_env_replaced(self, tmp_path, monkeypatch, fake_profile_dirs):
        monkeypatch.setenv("MY_API_KEY", "sk-real-key-123")
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {"api_key": "${MY_API_KEY}"},
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm["api_key"] == "sk-real-key-123"

    def test_env_missing_keeps_placeholder(self, monkeypatch, fake_profile_dirs):
        monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {"api_key": "${NONEXISTENT_VAR_XYZ}"},
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        # 缺失时保持原样（让后续 resolve 阶段报错或回退）
        assert cfg.llm["api_key"] == "${NONEXISTENT_VAR_XYZ}"

    def test_recursive_replacement_in_nested_dict(self, monkeypatch, fake_profile_dirs):
        monkeypatch.setenv("INNER_KEY", "inner-secret")
        monkeypatch.setenv("OUTER_KEY", "outer-secret")
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {
                    "api_key": "${INNER_KEY}",
                    "metadata": {
                        "alt_key": "${OUTER_KEY}",
                    },
                },
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm["api_key"] == "inner-secret"
        assert cfg.llm["metadata"]["alt_key"] == "outer-secret"

    def test_replacement_in_list(self, monkeypatch, fake_profile_dirs):
        monkeypatch.setenv("LIST_KEY", "list-secret")
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {
                    "fallback_keys": ["${LIST_KEY}", "literal"],
                },
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm["fallback_keys"] == ["list-secret", "literal"]

    def test_non_string_values_unchanged(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "enabled": True,
                },
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm["temperature"] == 0.7
        assert cfg.llm["max_tokens"] == 4096
        assert cfg.llm["enabled"] is True

    def test_partial_match_unchanged(self, monkeypatch, fake_profile_dirs):
        """$NOTBRACES 模式（非 ${} 形式）不替换"""
        monkeypatch.setenv("PARTIAL", "p")
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {"profile_id": "my_agent", "llm": {"api_key": "$PARTIAL-key"}},
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm["api_key"] == "$PARTIAL-key"


# ── 2) llm / image_gen 字段 + fallback ──────────────────────────────


class TestLLMSectionFallback:
    def test_agent_llm_returns_agent_config(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "llm": {"provider": "anthropic", "base_url": "https://a.example/v1"},
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm == {"provider": "anthropic", "base_url": "https://a.example/v1"}

    def test_agent_falls_back_to_system_llm(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "system-config" / "config.yaml",
            {
                "profile_id": "system-config",
                "llm": {"provider": "anthropic"},
            },
        )
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {"profile_id": "my_agent"},
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.llm == {"provider": "anthropic"}

    def test_returns_empty_dict_when_no_config_anywhere(
        self, monkeypatch, fake_profile_dirs
    ):
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {"profile_id": "my_agent"},
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        # 没有 llm 段就返回空 dict（不是 None）—— 调用方据此判断
        assert cfg.llm == {}


class TestImageGenSectionFallback:
    def test_agent_image_gen_returns_agent_config(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {
                "profile_id": "my_agent",
                "image_gen": {"provider": "openai", "model_id": "dall-e-3"},
            },
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.image_gen == {"provider": "openai", "model_id": "dall-e-3"}

    def test_agent_falls_back_to_system_image_gen(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "system-config" / "config.yaml",
            {
                "profile_id": "system-config",
                "image_gen": {"provider": "openai"},
            },
        )
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {"profile_id": "my_agent"},
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.image_gen == {"provider": "openai"}

    def test_returns_empty_dict_when_no_config(self, monkeypatch, fake_profile_dirs):
        write_yaml(
            fake_profile_dirs / "my_agent" / "config.yaml",
            {"profile_id": "my_agent"},
        )
        from src.agents.agent_config import AgentConfig
        cfg = AgentConfig(fake_profile_dirs / "my_agent")
        assert cfg.image_gen == {}
