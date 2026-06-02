"""
集成测试：per-agent LLM/生图配置的完整优先级链。

优先级（从高到低）：
  1. runtime override (override_store.llm_override / image_gen_override)
  2. agent config.yaml (AgentConfig.llm / image_gen)
  3. system-config 默认 (system-config/config.yaml 的 llm/image_gen 段)
  4. 全局 settings.llm / image_gen.active_provider

不实例化 AIAgent（避免依赖 hermes-agent），只验证 resolve 链。
"""
from __future__ import annotations

import os
import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("ENVIRONMENT", "testing")

from src.core.config import settings  # noqa: E402
from src.core import secret_cipher  # noqa: E402
from src.core.override_store import AgentOverrideStore  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """每个测试用独立 cipher key + 独立 override store 文件"""
    from src.core import override_store
    monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", Fernet.generate_key().decode())
    secret_cipher._cached_key = None
    monkeypatch.setattr(override_store, "OVERRIDES_FILE", tmp_path / "overrides.json")
    yield
    secret_cipher._cached_key = None


def _resolve_for_agent_in_priority(agent_id, yaml_llm=None, yaml_image_gen=None, system_llm=None, system_image_gen=None):
    """
    模拟 create_ai_agent() 内部的 resolve 流程，不实例化 AIAgent。

    返回 (resolved_llm, resolved_image_gen) dict。
    """
    from src.core.override_store import AgentOverrideStore
    store = AgentOverrideStore()
    llm_runtime = store.get_llm_override(agent_id) or {}
    img_runtime = store.get_image_gen_override(agent_id) or {}

    merged_llm = {**(yaml_llm or {}), **llm_runtime}
    merged_img = {**(yaml_image_gen or {}), **img_runtime}

    # 模拟 system-default：传给 resolve 时如果 provider 改了，base_url/api_key/model
    # 会从对应 provider 的全局配置取。这里我们直接调 settings 解析。
    resolved_llm = settings.llm.resolve_for_agent(merged_llm)
    resolved_img = settings.image_gen.resolve_for_agent(merged_img)
    return resolved_llm, resolved_img


class TestGlobalOnly:
    def test_no_yaml_no_override_uses_global(self):
        resolved_llm, _ = _resolve_for_agent_in_priority("agent.x")
        assert resolved_llm["provider"] == settings.llm.active_provider
        assert resolved_llm["api_key"] is not None


class TestYAMLPriority:
    def test_yaml_base_url_overrides_global(self):
        resolved_llm, _ = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_llm={"base_url": "https://yaml-base.example/v1"},
        )
        assert resolved_llm["base_url"] == "https://yaml-base.example/v1"
        # api_key 仍从全局
        assert resolved_llm["api_key"] is not None


class TestRuntimePriority:
    def test_runtime_api_key_overrides_yaml(self):
        store = AgentOverrideStore()
        store.update_llm_override("agent.x", {"api_key": "runtime-key"})

        resolved_llm, _ = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_llm={"base_url": "https://yaml.example/v1", "api_key": "yaml-key"},
        )
        assert resolved_llm["api_key"] == "runtime-key"
        assert resolved_llm["base_url"] == "https://yaml.example/v1"  # yaml 仍生效

    def test_runtime_base_url_overrides_yaml(self):
        store = AgentOverrideStore()
        store.update_llm_override("agent.x", {"base_url": "https://runtime.example/v1"})

        resolved_llm, _ = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_llm={"base_url": "https://yaml.example/v1"},
        )
        assert resolved_llm["base_url"] == "https://runtime.example/v1"

    def test_clear_runtime_falls_back_to_yaml(self):
        store = AgentOverrideStore()
        store.update_llm_override("agent.x", {"api_key": "runtime-key"})
        store.clear_llm_override("agent.x")

        resolved_llm, _ = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_llm={"api_key": "yaml-key"},
        )
        assert resolved_llm["api_key"] == "yaml-key"


class TestFullPrecedenceChain:
    def test_runtime_beats_yaml_beats_global(self):
        """完整链：runtime > yaml > global"""
        store = AgentOverrideStore()
        store.update_llm_override("agent.x", {
            "api_key": "runtime-key",
            "base_url": "https://runtime.example/v1",
            "model": "gpt-4o",
        })

        resolved_llm, _ = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_llm={
                "api_key": "yaml-key",
                "base_url": "https://yaml.example/v1",
                "model": "gpt-4o-mini",
            },
        )
        assert resolved_llm["api_key"] == "runtime-key"
        assert resolved_llm["base_url"] == "https://runtime.example/v1"
        assert resolved_llm["model_id"] == "gpt-4o"

    def test_runtime_encrypted_at_rest(self):
        """运行时存的 key 必须是密文（验证存盘安全）"""
        store = AgentOverrideStore()
        store.update_llm_override("agent.x", {"api_key": "super-secret"})

        raw = store.get_agent("agent.x")["llm_override"]["api_key"]
        assert raw.startswith("enc:")
        assert raw != "super-secret"

        # 通过 get_llm_override 读出明文
        assert store.get_llm_override("agent.x")["api_key"] == "super-secret"


class TestImageGenPrecedence:
    def test_yaml_image_gen_used(self):
        _, resolved_img = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_image_gen={"provider": "openai", "model_id": "dall-e-3"},
        )
        assert resolved_img["provider"] == "openai"
        assert resolved_img["model_id"] == "dall-e-3"

    def test_runtime_image_gen_overrides_yaml(self):
        store = AgentOverrideStore()
        store.update_image_gen_override("agent.x", {"model_id": "dall-e-2"})

        _, resolved_img = _resolve_for_agent_in_priority(
            "agent.x",
            yaml_image_gen={"provider": "openai", "model_id": "dall-e-3"},
        )
        assert resolved_img["model_id"] == "dall-e-2"
