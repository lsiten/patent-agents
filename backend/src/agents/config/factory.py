"""Factory for creating Hermes `AIAgent` instances."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from . import paths
from .registry import get_agent_config_registry
from .skills import build_profile_skill_prompt

logger = logging.getLogger(__name__)


def _wrap_status_callback(callback):
    if not callback:
        return None

    def _status(kind: Any, message: Any) -> None:
        status_message = str(message or "")
        normalized = status_message.lower()
        if "fallback" in normalized:
            if "max retries" in normalized or "retry" in normalized:
                status_message = "模型请求失败，未启用备用模型，正在返回真实错误。"
            else:
                return
        callback(kind, status_message)

    return _status


def create_ai_agent(
    profile_id: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    callbacks: Optional[Dict[str, Any]] = None,
    extra_system_prompt: Optional[str] = None,
    skill_name: Optional[str] = None,
):
    """Create a `run_agent.AIAgent` from one Hermes profile."""
    from run_agent import AIAgent
    from src.core.config import settings

    registry = get_agent_config_registry()
    registry.ensure_patent_tools()

    config = registry.get(profile_id)
    if not config:
        raise ValueError(f"Agent config not found: {profile_id}")

    profile_home = paths.HERMES_PROFILES_DIR / config.dir_path.name
    os.environ["HERMES_HOME"] = str(profile_home if profile_home.exists() else paths.HERMES_HOME_DIR)

    try:
        from src.agents.config.overrides import get_override_store

        override_store = get_override_store()
        runtime_overrides = override_store.get_config_overrides(profile_id)
        llm_runtime = override_store.get_llm_override(profile_id) or {}
        image_gen_runtime = override_store.get_image_gen_override(profile_id) or {}
    except Exception:
        runtime_overrides = {}
        llm_runtime = {}
        image_gen_runtime = {}

    merged_llm: Dict[str, Any] = {**(config.llm or {}), **llm_runtime}
    resolved_llm = settings.llm.resolve_for_agent(merged_llm)
    base_url = resolved_llm.get("base_url") or ""
    api_key = resolved_llm.get("api_key") or ""
    default_model = resolved_llm.get("model_id") or "gpt-4-turbo-preview"
    api_mode = settings.llm.api_mode

    merged_image_gen: Dict[str, Any] = {**(config.image_gen or {}), **image_gen_runtime}
    resolved_image_gen = settings.image_gen.resolve_for_agent(merged_image_gen)

    model = runtime_overrides.get("model") or (config.model if config.model != "default" else None) or default_model
    temperature = runtime_overrides.get("temperature", config.temperature)
    max_tokens = runtime_overrides.get("max_tokens", config.max_tokens)
    final_api_mode = config.api_mode or api_mode or runtime_overrides.get("api_mode")

    cb = callbacks or {}
    
    if skill_name:
        skills_for_prompt = [skill for skill in config.skills if skill.get("name") == skill_name]
    else:
        skills_for_prompt = config.skills
    
    skill_prompt = build_profile_skill_prompt(skills_for_prompt)
    system_prompt = config.soul_md
    if skill_prompt:
        system_prompt = f"{system_prompt.rstrip()}\n\n{skill_prompt}"
    
    # 如果有额外的system prompt，添加到末尾
    if extra_system_prompt:
        system_prompt = f"{system_prompt.rstrip()}\n\n{extra_system_prompt}"

    agent = AIAgent(
        base_url=base_url or None,
        api_key=api_key or None,
        model=model,
        api_mode=final_api_mode,
        max_iterations=config.max_iterations,
        max_tokens=max_tokens,
        enabled_toolsets=config.enabled_toolsets,
        ephemeral_system_prompt=system_prompt,
        session_id=session_id,
        user_id=user_id,
        quiet_mode=True,
        tool_progress_callback=cb.get("tool_progress"),
        tool_start_callback=cb.get("tool_start"),
        tool_complete_callback=cb.get("tool_complete"),
        thinking_callback=cb.get("thinking"),
        stream_delta_callback=cb.get("stream_delta"),
        status_callback=_wrap_status_callback(cb.get("status")),
        platform="api",
    )

    agent._fallback_chain = []
    agent._fallback_index = 0
    agent._fallback_model = None
    agent._fallback_activated = False

    logger.info(
        "AIAgent created: profile=%s, model=%s, temperature=%s, "
        "llm_provider=%s, llm_base_url=%s, image_gen_provider=%s, image_gen_base_url=%s, "
        "tools=%s, toolsets=%s",
        profile_id,
        model,
        temperature,
        resolved_llm.get("provider"),
        base_url,
        resolved_image_gen.get("provider"),
        resolved_image_gen.get("base_url"),
        len(agent.tools),
        config.enabled_toolsets,
    )

    return agent
