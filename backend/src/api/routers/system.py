import os
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger

from src.api.runtime_state import tasks_store, workflow_lock
from src.api.schemas import (
    ModelConfigSectionResponse,
    ModelConfigSectionUpdate,
    ProviderConfigResponse,
    SystemConfigResponse,
    SystemConfigUpdateRequest,
    SystemStatusResponse,
)
from src.core.constants.environment import DEFAULT_ENVIRONMENT, ENV_FILE_BY_ENVIRONMENT
from src.core.llm.providers import (
    DEFAULT_IMAGE_GEN_PROVIDER,
    DEFAULT_TEXT_LLM_PROVIDER,
    IMAGE_GEN_ENV_MAP,
    TEXT_LLM_ENV_MAP,
)
from src.knowledge.base import get_knowledge_base
from src.models.enums import WorkflowState

router = APIRouter(tags=["system"])

_LLM_ENV_MAP: Dict[str, Dict[str, str]] = dict(TEXT_LLM_ENV_MAP)
_IMG_ENV_MAP: Dict[str, Dict[str, str]] = dict(IMAGE_GEN_ENV_MAP)


def _get_env_file_path() -> tuple[str, str]:
    env = os.getenv("ENVIRONMENT", DEFAULT_ENVIRONMENT)
    filename = ENV_FILE_BY_ENVIRONMENT.get(env, ENV_FILE_BY_ENVIRONMENT[DEFAULT_ENVIRONMENT])
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(backend_dir, filename), env


def _get_env_value(values: dict, *keys: str) -> str:
    for key in keys:
        val = values.get(key)
        if val:
            return val
    return ""


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return key[:4] + "****"
    return key[:8] + "****"


def _read_config_from_env_file(env_path: str) -> SystemConfigResponse:
    from dotenv import dotenv_values

    values = dotenv_values(env_path)

    llm_providers: Dict[str, ProviderConfigResponse] = {}
    for provider, mapping in _LLM_ENV_MAP.items():
        api_key = _get_env_value(values, mapping["api_key"])
        base_url = _get_env_value(values, mapping["base_url"])
        model_id = _get_env_value(values, mapping["model_id"])
        llm_providers[provider] = ProviderConfigResponse(
            base_url=base_url,
            model_id=model_id,
            api_key_masked=_mask_key(api_key),
            configured=bool(api_key),
        )

    img_providers: Dict[str, ProviderConfigResponse] = {}
    for provider, mapping in _IMG_ENV_MAP.items():
        api_key = _get_env_value(values, mapping["api_key"])
        base_url = _get_env_value(values, mapping["base_url"])
        model_id = _get_env_value(values, mapping["model_id"])
        img_providers[provider] = ProviderConfigResponse(
            base_url=base_url,
            model_id=model_id,
            api_key_masked=_mask_key(api_key),
            configured=bool(api_key),
        )

    llm_active = _get_env_value(values, "LLM_ACTIVE_PROVIDER") or DEFAULT_TEXT_LLM_PROVIDER
    img_active = _get_env_value(values, "IMAGE_GEN_ACTIVE_PROVIDER") or DEFAULT_IMAGE_GEN_PROVIDER

    return SystemConfigResponse(
        text_llm=ModelConfigSectionResponse(active_provider=llm_active, providers=llm_providers),
        image_gen=ModelConfigSectionResponse(active_provider=img_active, providers=img_providers),
    )


@router.get("/system/config", response_model=SystemConfigResponse)
async def get_system_config():
    env_path, _ = _get_env_file_path()
    if not os.path.isfile(env_path):
        raise HTTPException(status_code=400, detail=f"配置文件不存在: {os.path.basename(env_path)}")
    return _read_config_from_env_file(env_path)


@router.put("/system/config", response_model=SystemConfigResponse)
async def update_system_config(body: SystemConfigUpdateRequest):
    from dotenv import set_key

    env_path, _ = _get_env_file_path()
    if not os.path.isfile(env_path):
        raise HTTPException(status_code=400, detail=f"配置文件不存在: {os.path.basename(env_path)}")

    def apply_updates(
        section: str,
        env_map: Dict[str, Dict[str, str]],
        updates: Optional[ModelConfigSectionUpdate],
    ) -> None:
        if not updates:
            return
        if updates.active_provider is not None:
            set_key(env_path, f"{section}_ACTIVE_PROVIDER", updates.active_provider)
        if updates.providers:
            for provider, cfg in updates.providers.items():
                mapping = env_map.get(provider)
                if not mapping:
                    continue
                if cfg.base_url is not None and mapping.get("base_url"):
                    set_key(env_path, mapping["base_url"], cfg.base_url)
                if cfg.api_key is not None and mapping.get("api_key"):
                    set_key(env_path, mapping["api_key"], cfg.api_key)
                if cfg.model_id is not None and mapping.get("model_id"):
                    set_key(env_path, mapping["model_id"], cfg.model_id)

    apply_updates("LLM", _LLM_ENV_MAP, body.text_llm)
    apply_updates("IMAGE_GEN", _IMG_ENV_MAP, body.image_gen)

    try:
        from src.core.config import reload_settings

        reload_settings()
    except Exception as exc:
        logger.warning(f"热重载配置失败（不影响文件写入）: {exc}")

    return _read_config_from_env_file(env_path)


@router.get("/system/config/env-info")
async def get_system_config_env_info():
    env_path, env_name = _get_env_file_path()
    return {
        "environment": env_name,
        "env_file": os.path.basename(env_path),
        "env_file_exists": os.path.isfile(env_path),
    }


@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status():
    async with workflow_lock:
        active_tasks = sum(
            1
            for task in tasks_store.values()
            if task.current_state not in [WorkflowState.COMPLETED, WorkflowState.FAILED]
        )

    kb = get_knowledge_base()

    return SystemStatusResponse(
        status="running",
        active_tasks=active_tasks,
        agents=[
            {"name": "CEO Agent", "description": "全局流程调度", "status": "idle"},
            {"name": "需求分析Agent", "description": "技术需求结构化", "status": "idle"},
            {"name": "检索分析Agent", "description": "专利性评估", "status": "idle"},
            {"name": "专利撰写Agent", "description": "申请文件生成", "status": "idle"},
            {"name": "质量审查Agent", "description": "合规性检查", "status": "idle"},
        ],
        knowledge_base_count=len(kb.list_all_patents()),
        data_sources=["google_patents", "uspto", "arxiv"],
    )


@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
