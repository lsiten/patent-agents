"""Built-in provider definitions.

This module is the single home for non-secret built-in LLM/image provider
metadata: provider ids, default endpoints, default model ids, and env var names.
API keys remain external configuration and must not be committed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ProviderDefinition:
    """Static metadata for one text or image model provider."""

    provider_id: str
    display_name: str
    category: str
    base_url_env: str
    model_env: str
    default_base_url: str
    default_model: str
    api_key_env: Optional[str] = None
    api_secret_env: Optional[str] = None
    openai_compatible: bool = True


DEFAULT_TEXT_LLM_PROVIDER = "openai"
DEFAULT_IMAGE_GEN_PROVIDER = "azure_aoai"


TEXT_LLM_PROVIDER_DEFINITIONS: Dict[str, ProviderDefinition] = {
    "openai": ProviderDefinition(
        provider_id="openai",
        display_name="OpenAI / OpenAI-compatible",
        category="text_llm",
        api_key_env="LLM_OPENAI_API_KEY",
        base_url_env="LLM_OPENAI_BASE_URL",
        model_env="LLM_OPENAI_MODEL",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4-turbo-preview",
    ),
    "anthropic": ProviderDefinition(
        provider_id="anthropic",
        display_name="Anthropic Claude",
        category="text_llm",
        api_key_env="LLM_ANTHROPIC_API_KEY",
        base_url_env="LLM_ANTHROPIC_BASE_URL",
        model_env="LLM_ANTHROPIC_MODEL",
        default_base_url="https://api.anthropic.com/v1",
        default_model="claude-3-opus-20240229",
        openai_compatible=False,
    ),
    "deepseek": ProviderDefinition(
        provider_id="deepseek",
        display_name="DeepSeek",
        category="text_llm",
        api_key_env="LLM_DEEPSEEK_API_KEY",
        base_url_env="LLM_DEEPSEEK_BASE_URL",
        model_env="LLM_DEEPSEEK_MODEL",
        default_base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
    ),
    "openrouter": ProviderDefinition(
        provider_id="openrouter",
        display_name="OpenRouter",
        category="text_llm",
        api_key_env="LLM_OPENROUTER_API_KEY",
        base_url_env="LLM_OPENROUTER_BASE_URL",
        model_env="LLM_OPENROUTER_MODEL",
        default_base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/auto",
    ),
    "spark": ProviderDefinition(
        provider_id="spark",
        display_name="讯飞星火",
        category="text_llm",
        api_key_env="LLM_SPARK_API_KEY",
        api_secret_env="LLM_SPARK_API_SECRET",
        base_url_env="LLM_SPARK_BASE_URL",
        model_env="LLM_SPARK_MODEL",
        default_base_url="https://spark-api-open.xf-yun.com/v1",
        default_model="generalv3.5",
    ),
    "openai-spark": ProviderDefinition(
        provider_id="openai-spark",
        display_name="讯飞星火 OpenAI-compatible",
        category="text_llm",
        api_key_env="LLM_SPARK_API_KEY",
        api_secret_env="LLM_SPARK_API_SECRET",
        base_url_env="LLM_SPARK_BASE_URL",
        model_env="LLM_SPARK_MODEL",
        default_base_url="https://spark-api-open.xf-yun.com/v1",
        default_model="generalv3.5",
    ),
}


IMAGE_GEN_PROVIDER_DEFINITIONS: Dict[str, ProviderDefinition] = {
    "azure_aoai": ProviderDefinition(
        provider_id="azure_aoai",
        display_name="Azure OpenAI image proxy",
        category="image_gen",
        api_key_env="IMAGE_GEN_AZURE_AOAI_API_KEY",
        base_url_env="IMAGE_GEN_AZURE_AOAI_BASE_URL",
        model_env="IMAGE_GEN_AZURE_AOAI_MODEL_ID",
        default_base_url="http://deepseek-work.intsig.net/proxy/azure/gpt/v1",
        default_model="gpt-image-2",
    ),
    "openai": ProviderDefinition(
        provider_id="openai",
        display_name="OpenAI Images",
        category="image_gen",
        api_key_env="IMAGE_GEN_OPENAI_API_KEY",
        base_url_env="IMAGE_GEN_OPENAI_BASE_URL",
        model_env="IMAGE_GEN_OPENAI_MODEL_ID",
        default_base_url="https://api.openai.com/v1",
        default_model="dall-e-3",
    ),
    "stability": ProviderDefinition(
        provider_id="stability",
        display_name="Stability AI",
        category="image_gen",
        api_key_env="IMAGE_GEN_STABILITY_API_KEY",
        base_url_env="IMAGE_GEN_STABILITY_BASE_URL",
        model_env="IMAGE_GEN_STABILITY_MODEL_ID",
        default_base_url="https://api.stability.ai/v1",
        default_model="stable-diffusion-3",
    ),
}


TEXT_LLM_PROVIDERS = frozenset(TEXT_LLM_PROVIDER_DEFINITIONS.keys())
IMAGE_GEN_PROVIDERS = frozenset(IMAGE_GEN_PROVIDER_DEFINITIONS.keys())


def _env_map(definitions: Dict[str, ProviderDefinition]) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    for provider_id, definition in definitions.items():
        mapping = {
            "base_url": definition.base_url_env,
            "model_id": definition.model_env,
        }
        if definition.api_key_env:
            mapping["api_key"] = definition.api_key_env
        if definition.api_secret_env:
            mapping["api_secret"] = definition.api_secret_env
        result[provider_id] = mapping
    return result


TEXT_LLM_ENV_MAP = _env_map(TEXT_LLM_PROVIDER_DEFINITIONS)
IMAGE_GEN_ENV_MAP = _env_map(IMAGE_GEN_PROVIDER_DEFINITIONS)
