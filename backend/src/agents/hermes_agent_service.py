"""
Hermes Agent Service — 基于真实 hermes-agent (NousResearch) 的 Agent 服务层

将项目中的 6 个专利 Agent 实例化为真正的 hermes-agent AIAgent，
提供统一的调用接口供 FastAPI routes 使用。

配置策略：
- HERMES_HOME 指向项目的 backend/hermes_home/ 目录（而非 ~/.hermes）
- LLM 配置从项目 settings (core/config.py) 读取
- 前端修改的配置（temperature, model）通过 override_store 传入 AIAgent
"""
import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Agent 配置目录
AGENTS_CONFIG_DIR = Path(__file__).parent.parent.parent / "hermes_agents"

# Hermes Home 重定向到项目目录（而非 ~/.hermes）
HERMES_HOME_DIR = Path(__file__).parent.parent.parent / "hermes_home"
HERMES_HOME_DIR.mkdir(parents=True, exist_ok=True)

# 在模块加载时设置 HERMES_HOME 环境变量
os.environ["HERMES_HOME"] = str(HERMES_HOME_DIR)


class HermesAgentConfig:
    """单个 Agent 的配置"""

    def __init__(self, dir_path: Path):
        self.dir_path = dir_path
        self.config = self._load_config()
        self.soul_md = self._load_soul()

    def _load_config(self) -> Dict[str, Any]:
        config_path = self.dir_path / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_soul(self) -> str:
        soul_path = self.dir_path / "SOUL.md"
        if soul_path.exists():
            with open(soul_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    @property
    def profile_id(self) -> str:
        return self.config.get("profile_id", "")

    @property
    def name(self) -> str:
        return self.config.get("name", "")

    @property
    def description(self) -> str:
        return self.config.get("description", "")

    @property
    def role(self) -> str:
        return self.config.get("role", "specialist")

    @property
    def model(self) -> str:
        return self.config.get("model", "default")

    @property
    def temperature(self) -> float:
        return self.config.get("temperature", 0.7)

    @property
    def max_tokens(self) -> int:
        return self.config.get("max_tokens", 4096)

    @property
    def enabled_tools(self) -> List[str]:
        return self.config.get("enabled_tools", [])

    @property
    def enabled_toolsets(self) -> List[str]:
        return self.config.get("enabled_toolsets", ["patent"])

    @property
    def skills(self) -> List[Dict[str, Any]]:
        """从 skills/ 目录加载技能"""
        skills_dir = self.dir_path / "skills"
        if not skills_dir.exists():
            return []
        skills = []
        for md_file in skills_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem.replace("_", " ")
            # 提取描述（第一段非标题文本）
            lines = content.split("\n")
            desc = ""
            for line in lines:
                if line and not line.startswith("#"):
                    desc = line.strip()
                    break
            skills.append({"name": name, "description": desc, "file": str(md_file.name)})
        return skills

    def save_config(self) -> None:
        """保存配置到 YAML"""
        config_path = self.dir_path / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def save_soul(self) -> None:
        """保存 SOUL.md"""
        soul_path = self.dir_path / "SOUL.md"
        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(self.soul_md)


class HermesAgentService:
    """
    基于真实 hermes-agent 的 Agent 服务

    管理 6 个专利 Agent 的生命周期、配置和调用。
    每次对话创建一个 AIAgent 实例，使用对应的配置。
    """

    def __init__(self):
        self._configs: Dict[str, HermesAgentConfig] = {}
        self._lock = threading.Lock()
        self._patent_tools_registered = False
        self._load_all_configs()

    def _load_all_configs(self) -> None:
        """加载所有 Agent 配置"""
        if not AGENTS_CONFIG_DIR.exists():
            logger.warning("Agent config directory not found: %s", AGENTS_CONFIG_DIR)
            return

        for subdir in AGENTS_CONFIG_DIR.iterdir():
            if subdir.is_dir() and (subdir / "config.yaml").exists():
                config = HermesAgentConfig(subdir)
                self._configs[config.profile_id] = config
                logger.info("Loaded agent config: %s (%s)", config.name, config.profile_id)

    def _ensure_patent_tools(self) -> None:
        """确保专利工具已注册到 hermes-agent registry"""
        if self._patent_tools_registered:
            return
        with self._lock:
            if self._patent_tools_registered:
                return
            from src.agents.hermes.tools.adapter import init_patent_tools
            init_patent_tools()
            self._patent_tools_registered = True
            logger.info("Patent tools registered to hermes-agent")

    def get_all_configs(self) -> List[HermesAgentConfig]:
        """获取所有 Agent 配置"""
        return list(self._configs.values())

    def get_config(self, profile_id: str) -> Optional[HermesAgentConfig]:
        """获取单个 Agent 配置"""
        return self._configs.get(profile_id)

    def create_agent_instance(
        self,
        profile_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        callbacks: Optional[Dict[str, Callable]] = None,
    ):
        """
        创建一个 AIAgent 实例

        LLM 配置优先级：
        1. 前端 override (override_store 中用户修改的 model/temperature)
        2. Agent config.yaml 中的配置
        3. 项目 settings (.env 中的 OPENAI_API_KEY, LLM_MODEL 等)

        Args:
            profile_id: Agent 配置 ID
            session_id: 会话 ID
            user_id: 用户 ID
            callbacks: 回调函数

        Returns:
            AIAgent 实例
        """
        self._ensure_patent_tools()

        config = self._configs.get(profile_id)
        if not config:
            raise ValueError(f"Agent config not found: {profile_id}")

        from run_agent import AIAgent

        # 从项目 settings 获取 LLM 基础配置
        try:
            from src.core.config import settings
            api_key = settings.llm.api_key
            base_url = settings.llm.base_url
            default_model = settings.llm.llm_model
        except Exception:
            # Fallback to env vars
            api_key = os.environ.get("OPENAI_API_KEY", "")
            base_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("LLM_BASE_URL", ""))
            default_model = os.environ.get("LLM_MODEL", "gpt-4-turbo")

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

        cb = callbacks or {}

        agent = AIAgent(
            base_url=base_url or None,
            api_key=api_key or None,
            model=model,
            max_iterations=config.config.get("max_iterations", 20),
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

        return agent

    async def run_conversation(
        self,
        profile_id: str,
        user_input: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        callbacks: Optional[Dict[str, Callable]] = None,
    ) -> str:
        """
        运行 Agent 对话（异步）

        Args:
            profile_id: Agent 配置 ID
            user_input: 用户输入
            session_id: 会话 ID
            user_id: 用户 ID
            callbacks: 回调

        Returns:
            Agent 回复文本
        """
        agent = self.create_agent_instance(
            profile_id=profile_id,
            session_id=session_id,
            user_id=user_id,
            callbacks=callbacks,
        )

        # AIAgent.run_conversation 是同步的，需要在线程中运行
        result = await asyncio.to_thread(agent.run_conversation, user_input)
        return result

    async def run_conversation_stream(
        self,
        profile_id: str,
        user_input: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行 Agent 对话（流式，SSE 事件）

        使用 hermes-agent 的回调机制：
        - stream_delta_callback(delta) — 逐 token 文本流
        - tool_start_callback(call_id, name, args) — 工具调用开始
        - tool_complete_callback(call_id, name, args, result) — 工具调用完成
        - thinking_callback(data) — 思考过程
        - status_callback(kind, msg) — 状态变化

        Yields:
            {"type": "thinking|tool_call_start|tool_call_end|content_delta|content|done|error", "data": {...}}
        """
        events: List[Dict[str, Any]] = []
        events_lock = threading.Lock()
        content_chunks: List[str] = []

        def on_thinking(data):
            with events_lock:
                events.append({"type": "thinking", "data": {"iteration": 1, "agent": profile_id, "message": str(data)}})

        def on_tool_start(call_id, name, args):
            with events_lock:
                params = {}
                if isinstance(args, str):
                    try:
                        params = json.loads(args)
                    except Exception:
                        params = {"raw": args[:200]}
                elif isinstance(args, dict):
                    params = args
                events.append({"type": "tool_call_start", "data": {"name": name, "parameters": params}})

        def on_tool_complete(call_id, name, args, result):
            with events_lock:
                result_str = str(result)[:500] if result else ""
                events.append({"type": "tool_call_end", "data": {
                    "name": name,
                    "parameters": {},
                    "result": result_str,
                    "success": True,
                    "error": None,
                }})

        def on_stream_delta(delta):
            with events_lock:
                content_chunks.append(delta)
                events.append({"type": "content_delta", "data": {"delta": delta}})

        def on_status(kind, msg):
            with events_lock:
                events.append({"type": "status", "data": {"kind": kind, "message": msg}})

        callbacks = {
            "thinking": on_thinking,
            "tool_start": on_tool_start,
            "tool_complete": on_tool_complete,
            # 注意：不传 stream_delta_callback，让 hermes-agent 在 final_response 中返回完整回复
            # 如果传了 stream_delta，hermes-agent 可能流式输出但不填充 final_response
            "status": on_status,
        }

        # 在后台线程运行 Agent
        result_holder: Dict[str, Any] = {"result": None, "error": None, "done": False}

        def run_agent():
            try:
                agent = self.create_agent_instance(
                    profile_id=profile_id,
                    session_id=session_id,
                    callbacks=callbacks,
                )
                result_holder["result"] = agent.run_conversation(user_input)
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                result_holder["done"] = True

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        # 流式产出事件
        while not result_holder["done"] or events:
            with events_lock:
                batch = list(events)
                events.clear()

            for event in batch:
                yield event

            if not batch and not result_holder["done"]:
                await asyncio.sleep(0.05)

        # 最终结果
        if result_holder["error"]:
            yield {"type": "error", "data": {"error": result_holder["error"]}}
        else:
            # 提取 final_response
            result = result_holder["result"]
            if isinstance(result, dict):
                final_text = result.get("final_response", "") or ""
            else:
                final_text = str(result) if result else ""

            # 如果 stream_delta 有内容，用它拼接（streaming 模式下 final_response 可能为空）
            if content_chunks:
                final_text = "".join(content_chunks)

            # 如果没有通过 stream_delta 收到内容且 final_text 非空，发送完整回复
            if not content_chunks and final_text:
                yield {"type": "content", "data": {"content": final_text, "has_recommendation": "[CREATE_PATENT_RECOMMENDATION]" in final_text}}

            clean_text = final_text.replace("[CREATE_PATENT_RECOMMENDATION]", "").strip()
            yield {"type": "done", "data": {
                "message": {
                    "id": str(threading.current_thread().ident),
                    "role": "assistant",
                    "content": clean_text,
                    "timestamp": "",
                    "type": "text",
                    "tool_calls": None,
                },
                "has_recommendation": "[CREATE_PATENT_RECOMMENDATION]" in final_text,
                "conversation_id": session_id or "",
            }}


# 全局单例
_service: Optional[HermesAgentService] = None


def get_hermes_agent_service() -> HermesAgentService:
    """获取全局 Hermes Agent 服务实例"""
    global _service
    if _service is None:
        _service = HermesAgentService()
    return _service
