"""
Tests for per-agent LLM/ImageGen override in AgentOverrideStore.
验证：runtime override 存储时加密 api_key，读出时解密。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("ENVIRONMENT", "testing")


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """每个测试用独立的 overrides.json + 独立 master key"""
    from src.core import secret_cipher, override_store
    monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", Fernet.generate_key().decode())
    secret_cipher._cached_key = None

    monkeypatch.setattr(override_store, "OVERRIDES_FILE", tmp_path / "agent_overrides.json")
    yield
    secret_cipher._cached_key = None


class TestLLMOverride:
    def test_get_returns_none_when_unset(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        assert store.get_llm_override("agent.a") is None

    def test_update_stores_encrypted_api_key(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {
            "provider": "openai",
            "base_url": "https://x.example/v1",
            "api_key": "sk-plain-text",
            "model": "gpt-4o",
        })

        raw = store.get_agent("agent.a")["llm_override"]
        assert raw["api_key"].startswith("enc:")
        assert raw["api_key"] != "sk-plain-text"  # 真的被加密了
        assert raw["provider"] == "openai"
        assert raw["base_url"] == "https://x.example/v1"
        assert raw["model"] == "gpt-4o"

    def test_get_decrypts_api_key(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {"api_key": "real-secret"})
        result = store.get_llm_override("agent.a")
        assert result["api_key"] == "real-secret"

    def test_update_without_api_key_works(self):
        """只改 base_url 不传 api_key 时不创建加密条目"""
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {"base_url": "https://x.example/v1"})
        result = store.get_llm_override("agent.a")
        assert result["base_url"] == "https://x.example/v1"
        assert "api_key" not in result

    def test_clear_removes_override(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {"api_key": "k"})
        assert store.get_llm_override("agent.a") is not None
        store.clear_llm_override("agent.a")
        assert store.get_llm_override("agent.a") is None

    def test_persistence_to_disk(self, tmp_path):
        """存盘后重新加载能解密"""
        from src.core.override_store import AgentOverrideStore
        s1 = AgentOverrideStore()
        s1.update_llm_override("agent.a", {"api_key": "persistent-secret"})

        # 重新构造 store 触发 load
        s2 = AgentOverrideStore()
        assert s2.get_llm_override("agent.a")["api_key"] == "persistent-secret"

    def test_update_preserves_other_agent(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {"api_key": "key-a"})
        store.update_llm_override("agent.b", {"api_key": "key-b"})
        assert store.get_llm_override("agent.a")["api_key"] == "key-a"
        assert store.get_llm_override("agent.b")["api_key"] == "key-b"


class TestImageGenOverride:
    def test_get_returns_none_when_unset(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        assert store.get_image_gen_override("agent.a") is None

    def test_update_stores_encrypted_api_key(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_image_gen_override("agent.a", {
            "provider": "openai",
            "api_key": "sk-img-plain",
            "model_id": "dall-e-3",
        })
        raw = store.get_agent("agent.a")["image_gen_override"]
        assert raw["api_key"].startswith("enc:")
        assert raw["model_id"] == "dall-e-3"

    def test_get_decrypts_api_key(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_image_gen_override("agent.a", {"api_key": "real-img-secret"})
        assert store.get_image_gen_override("agent.a")["api_key"] == "real-img-secret"

    def test_clear_removes_override(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_image_gen_override("agent.a", {"api_key": "k"})
        store.clear_image_gen_override("agent.a")
        assert store.get_image_gen_override("agent.a") is None


class TestCoexistenceWithOtherOverrides:
    """LLM/生图 override 不会破坏已有的 tools/skills/timers/config 字段"""

    def test_other_fields_preserved(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        # 已有路径
        store.toggle_tool("agent.a", "search_tool", False)
        store.update_config("agent.a", {"temperature": 0.3})
        # 新增路径
        store.update_llm_override("agent.a", {"api_key": "k"})
        store.update_image_gen_override("agent.a", {"api_key": "k2"})

        assert store.is_tool_disabled("agent.a", "search_tool")
        assert store.get_config_overrides("agent.a")["temperature"] == 0.3
        assert store.get_llm_override("agent.a")["api_key"] == "k"
        assert store.get_image_gen_override("agent.a")["api_key"] == "k2"

    def test_clear_llm_preserves_image_gen(self):
        from src.core.override_store import AgentOverrideStore
        store = AgentOverrideStore()
        store.update_llm_override("agent.a", {"api_key": "k1"})
        store.update_image_gen_override("agent.a", {"api_key": "k2"})

        store.clear_llm_override("agent.a")
        assert store.get_llm_override("agent.a") is None
        assert store.get_image_gen_override("agent.a")["api_key"] == "k2"
