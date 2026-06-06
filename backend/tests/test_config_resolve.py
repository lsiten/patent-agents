"""
Tests for per-agent LLM / ImageGen config resolution.

验证：每个 agent 可以独立配置 LLM/生图供应商，缺失时回退全局 active provider。
"""
from __future__ import annotations

import os
import pytest
from cryptography.fernet import Fernet

# 必须在导入 settings 前设置 testing 环境（避免 .env 干扰）
os.environ.setdefault("ENVIRONMENT", "testing")

from src.core.config import LLMSettings, ImageGenSettings  # noqa: E402
from src.core import secret_cipher  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cipher(tmp_path, monkeypatch):
    """每个测试用独立 env master key 隔离加密状态"""
    monkeypatch.setenv("AGENT_OVERRIDE_MASTER_KEY", Fernet.generate_key().decode())
    secret_cipher._cached_key = None
    yield
    secret_cipher._cached_key = None


def make_llm(**overrides) -> LLMSettings:
    """构造一个独立的 LLMSettings 实例用于测试（Pydantic v2 BaseSettings 需要 alias 名字）"""
    defaults = {
        "LLM_ACTIVE_PROVIDER": "openai",
        "LLM_OPENAI_API_KEY": "global-openai-key",
        "LLM_OPENAI_BASE_URL": "https://api.openai.com/v1",
        "LLM_OPENAI_MODEL": "gpt-4-turbo",
        "LLM_ANTHROPIC_API_KEY": "global-anthropic-key",
        "LLM_ANTHROPIC_BASE_URL": "https://api.anthropic.com/v1",
        "LLM_ANTHROPIC_MODEL": "claude-3-opus",
    }
    defaults.update({k.upper(): v for k, v in overrides.items()})
    return LLMSettings(**defaults)


# ── LLMSettings.resolve_for_agent ──────────────────────────────────────


class TestLLMResolveNoOverride:
    def test_returns_active_provider_global_config(self):
        s = make_llm()
        result = s.resolve_for_agent(None)
        assert result["provider"] == "openai"
        assert result["api_key"] == "global-openai-key"
        assert result["base_url"] == "https://api.openai.com/v1"
        assert result["model_id"] == "gpt-4-turbo"

    def test_returns_active_provider_global_config_with_empty_dict(self):
        s = make_llm()
        result = s.resolve_for_agent({})
        assert result["provider"] == "openai"


class TestLLMResolveProviderOverride:
    def test_provider_override_uses_other_provider_global(self):
        s = make_llm()
        result = s.resolve_for_agent({"provider": "anthropic"})
        assert result["provider"] == "anthropic"
        assert result["api_key"] == "global-anthropic-key"
        assert result["base_url"] == "https://api.anthropic.com/v1"
        assert result["model_id"] == "claude-3-opus"

    def test_invalid_provider_falls_back_to_active(self):
        s = make_llm()
        result = s.resolve_for_agent({"provider": "invalid_vendor"})
        assert result["provider"] == "openai"  # fall back
        assert result["api_key"] == "global-openai-key"


class TestLLMResolveFullOverride:
    def test_all_fields_overridden(self):
        s = make_llm()
        override = {
            "provider": "openai",
            "base_url": "https://custom-proxy.example.com/v1",
            "api_key": "agent-specific-key",
            "model": "gpt-4o-mini",
        }
        result = s.resolve_for_agent(override)
        assert result["provider"] == "openai"
        assert result["base_url"] == "https://custom-proxy.example.com/v1"
        assert result["api_key"] == "agent-specific-key"
        assert result["model_id"] == "gpt-4o-mini"

    def test_partial_override_fills_missing_from_global(self):
        s = make_llm()
        result = s.resolve_for_agent({"base_url": "https://custom.example/v1"})
        # base_url 来自 override
        assert result["base_url"] == "https://custom.example/v1"
        # 其他字段回退到全局 openai 配置
        assert result["api_key"] == "global-openai-key"
        assert result["model_id"] == "gpt-4-turbo"

    def test_provider_change_pulls_that_provider_global(self):
        """override provider 改为 anthropic，但保留自定义 base_url/api_key"""
        s = make_llm()
        result = s.resolve_for_agent({
            "provider": "anthropic",
            "base_url": "https://my-anthropic-proxy.example/v1",
            "api_key": "my-anthropic-key",
        })
        assert result["provider"] == "anthropic"
        assert result["base_url"] == "https://my-anthropic-proxy.example/v1"
        assert result["api_key"] == "my-anthropic-key"
        # model 未指定 → 用 anthropic 全局
        assert result["model_id"] == "claude-3-opus"


class TestLLMResolveDecryption:
    def test_encrypted_api_key_is_decrypted(self):
        s = make_llm()
        encrypted_key = secret_cipher.encrypt_value("real-secret-key")
        result = s.resolve_for_agent({"api_key": encrypted_key})
        assert result["api_key"] == "real-secret-key"

    def test_plain_api_key_passes_through(self):
        s = make_llm()
        result = s.resolve_for_agent({"api_key": "plain-text-key"})
        assert result["api_key"] == "plain-text-key"


class TestLLMResolveResponseShape:
    def test_returns_required_keys(self):
        s = make_llm()
        result = s.resolve_for_agent(None)
        assert set(result.keys()) >= {"provider", "base_url", "api_key", "model_id"}


# ── ImageGenSettings.resolve_for_agent ────────────────────────────────


def make_image_gen(**overrides) -> ImageGenSettings:
    defaults = {
        "IMAGE_GEN_ACTIVE_PROVIDER": "azure_aoai",
        "IMAGE_GEN_AZURE_AOAI_BASE_URL": "https://azure.example/v1",
        "IMAGE_GEN_AZURE_AOAI_API_KEY": "global-azure-key",
        "IMAGE_GEN_AZURE_AOAI_MODEL_ID": "gpt-image-2",
        "IMAGE_GEN_OPENAI_BASE_URL": "https://api.openai.com/v1",
        "IMAGE_GEN_OPENAI_API_KEY": "global-openai-img-key",
        "IMAGE_GEN_OPENAI_MODEL_ID": "dall-e-3",
    }
    defaults.update({k.upper(): v for k, v in overrides.items()})
    return ImageGenSettings(**defaults)


class TestImageGenResolveNoOverride:
    def test_returns_active_provider_global_config(self):
        s = make_image_gen()
        result = s.resolve_for_agent(None)
        assert result["provider"] == "azure_aoai"
        assert result["api_key"] == "global-azure-key"
        assert result["base_url"] == "https://azure.example/v1"
        assert result["model_id"] == "gpt-image-2"


class TestImageGenResolveProviderOverride:
    def test_provider_override_uses_openai_global(self):
        s = make_image_gen()
        result = s.resolve_for_agent({"provider": "openai"})
        assert result["provider"] == "openai"
        assert result["api_key"] == "global-openai-img-key"
        assert result["model_id"] == "dall-e-3"

    def test_invalid_provider_falls_back_to_active(self):
        s = make_image_gen()
        result = s.resolve_for_agent({"provider": "magic_vendor"})
        assert result["provider"] == "azure_aoai"


class TestImageGenResolveFullOverride:
    def test_all_fields_overridden(self):
        s = make_image_gen()
        result = s.resolve_for_agent({
            "provider": "openai",
            "base_url": "https://custom-img.example/v1",
            "api_key": "agent-img-key",
            "model_id": "dall-e-2",
        })
        assert result["provider"] == "openai"
        assert result["base_url"] == "https://custom-img.example/v1"
        assert result["api_key"] == "agent-img-key"
        assert result["model_id"] == "dall-e-2"

    def test_partial_override_fills_missing_from_global(self):
        s = make_image_gen()
        result = s.resolve_for_agent({"base_url": "https://x.example/v1"})
        assert result["base_url"] == "https://x.example/v1"
        assert result["api_key"] == "global-azure-key"
        assert result["model_id"] == "gpt-image-2"


class TestImageGenResolveDecryption:
    def test_encrypted_api_key_is_decrypted(self):
        s = make_image_gen()
        encrypted = secret_cipher.encrypt_value("real-img-secret")
        result = s.resolve_for_agent({"api_key": encrypted})
        assert result["api_key"] == "real-img-secret"


class TestImageGenResolveResponseShape:
    def test_returns_required_keys(self):
        s = make_image_gen()
        result = s.resolve_for_agent(None)
        assert set(result.keys()) >= {"provider", "base_url", "api_key", "model_id"}


class TestImageGenResolveWithLLMFallback:
    def test_uses_image_config_when_image_api_key_is_configured(self):
        image_gen = make_image_gen()
        llm = make_llm(
            llm_openai_api_key="llm-openai-key",
            llm_openai_base_url="https://llm.example/v1",
            llm_openai_model="gpt-4o",
        )

        result = image_gen.resolve_with_llm_fallback(llm)

        assert result["provider"] == "azure_aoai"
        assert result["api_key"] == "global-azure-key"
        assert result["base_url"] == "https://azure.example/v1"
        assert result["model_id"] == "gpt-image-2"

    def test_falls_back_to_llm_config_when_image_api_key_is_absent(self):
        image_gen = make_image_gen(
            image_gen_azure_aoai_api_key=None,
            image_gen_openai_api_key=None,
        )
        llm = make_llm(
            llm_openai_api_key="llm-openai-key",
            llm_openai_base_url="https://llm.example/v1",
            llm_openai_model="gpt-4o",
        )

        result = image_gen.resolve_with_llm_fallback(llm)

        assert result["provider"] == "openai"
        assert result["api_key"] == "llm-openai-key"
        assert result["base_url"] == "https://llm.example/v1"
        assert result["model_id"] == "gpt-image-2"

    def test_agent_image_override_is_applied_before_llm_fallback(self):
        image_gen = make_image_gen(
            image_gen_azure_aoai_api_key=None,
            image_gen_openai_api_key=None,
        )
        llm = make_llm(llm_openai_api_key="llm-openai-key")

        result = image_gen.resolve_with_llm_fallback(
            llm,
            {
                "provider": "openai",
                "base_url": "https://image-proxy.example/v1",
                "api_key": "agent-image-key",
                "model_id": "custom-image-model",
            },
        )

        assert result["provider"] == "openai"
        assert result["api_key"] == "agent-image-key"
        assert result["base_url"] == "https://image-proxy.example/v1"
        assert result["model_id"] == "custom-image-model"
