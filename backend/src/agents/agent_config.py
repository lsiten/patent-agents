"""
Agent 配置加载模块

从 hermes_home/profiles/ 目录加载 Agent 配置，提供给 AIAgent 实例化使用。
这是对 hermes-agent 的薄封装，不包含任何自定义 Agent 逻辑。
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import re

import yaml

logger = logging.getLogger(__name__)


def _parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """解析 SKILL.md 的 YAML frontmatter"""
    if not content.startswith("---"):
        return {}
    
    # 查找第二个 ---
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}

# Hermes Profiles 根目录
HERMES_HOME_DIR = Path(__file__).parent.parent.parent / "hermes_home"
HERMES_PROFILES_DIR = HERMES_HOME_DIR / "profiles"
SYSTEM_CONFIG_DIR = HERMES_PROFILES_DIR / "system-config"

# 确保目录存在并设置环境变量
HERMES_HOME_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HERMES_HOME", str(HERMES_HOME_DIR))

# 全局默认配置缓存
_system_defaults: Optional[Dict[str, Any]] = None


def _load_system_defaults() -> Dict[str, Any]:
    """加载 system-config 作为全局默认配置"""
    global _system_defaults
    if _system_defaults is not None:
        return _system_defaults
    
    config_path = SYSTEM_CONFIG_DIR / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _system_defaults = yaml.safe_load(f) or {}
                logger.info(f"Loaded system defaults from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load system defaults: {e}")
            _system_defaults = {}
    else:
        logger.warning(f"System config not found: {config_path}")
        _system_defaults = {}
    
    return _system_defaults


class AgentConfig:
    """单个 Agent 的配置，缺失字段时回退到 system-config 默认值"""

    def __init__(self, dir_path: Path):
        self.dir_path = dir_path
        self._config: Dict[str, Any] = {}
        self._soul_md: str = ""
        self._defaults: Dict[str, Any] = _load_system_defaults()
        self._load()

    def _load(self) -> None:
        """加载配置文件和 SOUL.md"""
        config_path = self.dir_path / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}

        soul_path = self.dir_path / "SOUL.md"
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as f:
                self._soul_md = f.read()

    def _get(self, key: str, fallback: Any = None) -> Any:
        """获取配置值，优先使用本地配置，否则回退到 system-config"""
        if key in self._config:
            return self._config[key]
        if key in self._defaults:
            return self._defaults[key]
        return fallback

    @property
    def profile_id(self) -> str:
        return self._get("profile_id", self.dir_path.name)

    @property
    def name(self) -> str:
        return self._get("name", self.profile_id)

    @property
    def description(self) -> str:
        return self._get("description", "")

    @property
    def role(self) -> str:
        return self._get("role", "specialist")

    @property
    def model(self) -> str:
        return self._get("model", "default")

    @property
    def temperature(self) -> float:
        return self._get("temperature", 0.7)

    @property
    def max_tokens(self) -> int:
        return self._get("max_tokens", 4096)

    @property
    def max_iterations(self) -> int:
        return self._get("max_iterations", 20)

    @property
    def enabled_tools(self) -> List[str]:
        return self._get("enabled_tools", [])

    @property
    def enabled_toolsets(self) -> List[str]:
        return self._get("enabled_toolsets", ["patent"])

    @property
    def api_mode(self) -> Optional[str]:
        return self._get("api_mode")

    @property
    def soul_md(self) -> str:
        return self._soul_md

    @property
    def raw_config(self) -> Dict[str, Any]:
        """返回原始配置字典"""
        return self._config.copy()

    @property
    def config(self) -> Dict[str, Any]:
        """返回原始配置字典（兼容别名）"""
        return self._config

    @property
    def skills(self) -> List[Dict[str, Any]]:
        """
        从 skills/ 目录读取所有技能
        
        返回格式：
        [
            {
                "name": "task-decomposition",
                "description": "将复杂的专利申请任务分解为可执行的子任务",
                "version": "1.0.0",
                "file": "task-decomposition/SKILL.md",
                "enabled": True,
                "tags": [...],
                "content": "..."  # SKILL.md 全文
            },
            ...
        ]
        """
        skills_dir = self.dir_path / "skills"
        if not skills_dir.exists():
            return []
        
        result = []
        for skill_subdir in skills_dir.iterdir():
            if not skill_subdir.is_dir():
                continue
            
            skill_file = skill_subdir / "SKILL.md"
            if not skill_file.exists():
                continue
            
            try:
                content = skill_file.read_text(encoding="utf-8")
                meta = _parse_skill_frontmatter(content)
                
                result.append({
                    "name": meta.get("name", skill_subdir.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "1.0.0"),
                    "file": f"{skill_subdir.name}/SKILL.md",
                    "enabled": meta.get("enabled", True),
                    "tags": meta.get("metadata", {}).get("tags", []),
                    "content": content,
                })
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_subdir.name}: {e}")
        
        return result


class AgentConfigRegistry:
    """Agent 配置注册表 - 管理所有 Agent 配置的加载和访问"""

    def __init__(self):
        self._configs: Dict[str, AgentConfig] = {}
        self._patent_tools_registered = False
        self._load_all()

    def _load_all(self) -> None:
        """从 profiles 目录加载所有 Agent 配置（排除 system-config）"""
        if not HERMES_PROFILES_DIR.exists():
            logger.warning(f"Profiles directory not found: {HERMES_PROFILES_DIR}")
            return

        for subdir in HERMES_PROFILES_DIR.iterdir():
            # 跳过 system-config，它是全局默认配置，不是 Agent
            if subdir.name == "system-config":
                continue
            if subdir.is_dir() and (subdir / "config.yaml").exists():
                try:
                    config = AgentConfig(subdir)
                    self._configs[config.profile_id] = config
                    logger.info(f"Loaded agent config: {config.name} ({config.profile_id})")
                except Exception as e:
                    logger.error(f"Failed to load config from {subdir}: {e}")

    def ensure_patent_tools(self) -> None:
        """确保专利工具已注册到 hermes-agent registry"""
        if self._patent_tools_registered:
            return
        try:
            from src.agents.hermes.tools.adapter import init_patent_tools
            init_patent_tools()
            self._patent_tools_registered = True
            logger.info("Patent tools registered to hermes-agent")
        except Exception as e:
            logger.error(f"Failed to register patent tools: {e}")

    def get(self, profile_id: str) -> Optional[AgentConfig]:
        """获取指定 Agent 的配置"""
        return self._configs.get(profile_id)

    def get_all(self) -> List[AgentConfig]:
        """获取所有 Agent 配置"""
        return list(self._configs.values())

    def list_ids(self) -> List[str]:
        """获取所有 Agent ID 列表"""
        return list(self._configs.keys())


# 全局单例
_registry: Optional[AgentConfigRegistry] = None


def get_agent_config_registry() -> AgentConfigRegistry:
    """获取全局 Agent 配置注册表"""
    global _registry
    if _registry is None:
        _registry = AgentConfigRegistry()
    return _registry


def get_agent_config(profile_id: str) -> Optional[AgentConfig]:
    """便捷函数：获取指定 Agent 的配置"""
    return get_agent_config_registry().get(profile_id)


def create_ai_agent(
    profile_id: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    callbacks: Optional[Dict[str, Any]] = None,
):
    """
    创建 AIAgent 实例

    Args:
        profile_id: Agent 配置 ID
        session_id: 会话 ID
        user_id: 用户 ID
        callbacks: 回调函数字典，支持:
            - tool_progress: 工具进度回调
            - tool_start: 工具开始回调 (call_id, name, args)
            - tool_complete: 工具完成回调 (call_id, name, args, result)
            - thinking: 思考过程回调
            - stream_delta: 流式文本回调
            - status: 状态回调

    Returns:
        AIAgent 实例
    """
    from run_agent import AIAgent

    registry = get_agent_config_registry()
    registry.ensure_patent_tools()

    config = registry.get(profile_id)
    if not config:
        raise ValueError(f"Agent config not found: {profile_id}")

    # 设置 Agent 专属的 HERMES_HOME
    profile_home = HERMES_PROFILES_DIR / config.dir_path.name
    if profile_home.exists():
        os.environ["HERMES_HOME"] = str(profile_home)
    else:
        os.environ["HERMES_HOME"] = str(HERMES_HOME_DIR)

    # 从项目 settings 获取 LLM 配置
    try:
        from src.core.config import settings
        api_key = settings.llm.api_key
        base_url = settings.llm.base_url
        default_model = settings.llm.openai_model
        api_mode = getattr(settings.llm, "api_mode", None)
    except Exception:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("LLM_BASE_URL", ""))
        default_model = os.environ.get("LLM_OPENAI_MODEL", "gpt-4-turbo")
        api_mode = None

    # 应用前端 override（用户在页面修改的配置）
    try:
        from src.core.override_store import get_override_store
        overrides = get_override_store().get_config_overrides(profile_id)
    except Exception:
        overrides = {}

    # 最终配置：override > agent config > project settings
    model = overrides.get("model") or (config.model if config.model != "default" else None) or default_model
    temperature = overrides.get("temperature", config.temperature)
    max_tokens = overrides.get("max_tokens", config.max_tokens)
    final_api_mode = config.api_mode or api_mode or overrides.get("api_mode")

    cb = callbacks or {}

    agent = AIAgent(
        base_url=base_url or None,
        api_key=api_key or None,
        model=model,
        api_mode=final_api_mode,
        max_iterations=config.max_iterations,
        max_tokens=max_tokens,
        enabled_toolsets=config.enabled_toolsets,
        ephemeral_system_prompt=config.soul_md,
        session_id=session_id,
        user_id=user_id,
        quiet_mode=True,
        tool_progress_callback=cb.get("tool_progress"),
        tool_start_callback=cb.get("tool_start"),
        tool_complete_callback=cb.get("tool_complete"),
        thinking_callback=cb.get("thinking"),
        stream_delta_callback=cb.get("stream_delta"),
        status_callback=cb.get("status"),
        platform="api",
    )

    logger.info(
        f"AIAgent created: profile={profile_id}, model={model}, "
        f"tools={len(agent.tools)}, toolsets={config.enabled_toolsets}"
    )

    return agent
