"""
LLM API 客户端封装
支持 OpenAI、Anthropic，提供统一接口、自动重试、Fallback、Token 计数
"""
import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from .config import settings
from .logging import get_logger

logger = get_logger("llm_client")


class LLMProvider(str, Enum):
    """LLM 提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class LLMMessage:
    """LLM 消息"""
    role: str  # system / user / assistant / function
    content: str
    name: Optional[str] = None  # 用于 function 调用
    function_call: Optional[Dict[str, Any]] = None

    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI 格式"""
        msg = {"role": self.role, "content": self.content}
        if self.name:
            msg["name"] = self.name
        if self.function_call:
            msg["function_call"] = self.function_call
        return msg

    def to_anthropic_format(self) -> Dict[str, Any]:
        """转换为 Anthropic 格式（注意：system 消息需要单独处理，不放入 messages 数组）"""
        msg = {"role": self.role, "content": self.content}
        return msg


@dataclass
class LLMFunctionCall:
    """LLM 函数调用结果"""
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str


@dataclass
class LLMResponse:
    """LLM 响应结果"""
    content: Optional[str] = None
    function_calls: List[LLMFunctionCall] = field(default_factory=list)
    model: str = ""
    provider: LLMProvider = LLMProvider.OPENAI
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    raw_response: Any = None

    @property
    def has_function_call(self) -> bool:
        return len(self.function_calls) > 0


@dataclass
class LLMTokenUsage:
    """Token 使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "LLMTokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


class LLMError(Exception):
    """LLM 基础错误"""
    pass


class LLMRateLimitError(LLMError):
    """限流错误"""
    pass


class LLMAuthError(LLMError):
    """认证错误"""
    pass


class LLMToolUseError(LLMError):
    """工具使用错误"""
    pass


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """聊天补全"""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """计算 Token 数量"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI 客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.llm.openai_api_key
        self.base_url = base_url or settings.llm.openai_base_url
        self.default_model = model or settings.llm.openai_model
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        self.timeout = settings.llm.timeout
        self.max_retries = settings.llm.max_retries
        self.retry_delay = settings.llm.retry_delay

        self._client = None
        self._client_init_lock = asyncio.Lock()
        self._token_usage = LLMTokenUsage()

        if not self.api_key:
            logger.warning("OpenAI API key not configured")

    async def _init_client(self):
        """初始化客户端（延迟初始化）"""
        if self._client is not None or not self.api_key:
            return

        async with self._client_init_lock:
            if self._client is not None:
                return
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
                logger.info("OpenAI client initialized")
            except ImportError:
                logger.warning("OpenAI package not installed")

    def count_tokens(self, text: str) -> int:
        """估算 Token 数量（简化版）"""
        # 简化估算：中文约 1 字 = 1.3 tokens，英文约 1 词 = 0.75 tokens
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.3 + other_chars * 0.25)

    async def chat_completion(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, str]] = None,
        **extra_kwargs,
    ) -> LLMResponse:
        """执行聊天补全，带自动重试"""
        start_time = time.perf_counter()

        await self._init_client()

        if self._client is None:
            raise LLMAuthError("OpenAI API key or package is not configured")

        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        openai_messages = [m.to_openai_format() for m in messages]

        for attempt in range(self.max_retries + 1):
            try:
                request_kwargs = {
                    "model": model,
                    "messages": openai_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                if tools:
                    request_kwargs["tools"] = tools
                    if tool_choice:
                        request_kwargs["tool_choice"] = tool_choice

                if response_format:
                    request_kwargs["response_format"] = response_format

                # 使用 asyncio.wait_for 防止请求永远挂起
                try:
                    response = await asyncio.wait_for(
                        self._client.chat.completions.create(**request_kwargs),
                        timeout=float(self.timeout),
                    )
                except asyncio.TimeoutError:
                    raise LLMError(f"LLM request timed out after {self.timeout}s")

                latency = (time.perf_counter() - start_time) * 1000

                # 解析响应
                choice = response.choices[0]
                result = LLMResponse(
                    content=choice.message.content,
                    model=response.model,
                    provider=LLMProvider.OPENAI,
                    latency_ms=latency,
                    raw_response=response,
                )

                # 解析 Token 使用
                if hasattr(response, "usage") and response.usage:
                    result.prompt_tokens = response.usage.prompt_tokens
                    result.completion_tokens = response.usage.completion_tokens
                    result.total_tokens = response.usage.total_tokens
                    self._token_usage.add(LLMTokenUsage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                    ))

                # 解析函数调用
                if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                    for tool_call in choice.message.tool_calls:
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            args = {}

                        result.function_calls.append(LLMFunctionCall(
                            name=tool_call.function.name,
                            arguments=args,
                            raw_arguments=tool_call.function.arguments,
                        ))

                logger.debug(
                    "OpenAI chat completion",
                    model=model,
                    latency_ms=round(latency),
                    tokens=result.total_tokens,
                    has_function_call=result.has_function_call,
                )

                return result

            except Exception as e:
                if "rate limit" in str(e).lower() or "429" in str(e):
                    if attempt < self.max_retries:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.warning(
                            "Rate limit hit, retrying",
                            attempt=attempt + 1,
                            delay_seconds=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise LLMRateLimitError(f"Rate limit exceeded after {self.max_retries} retries: {e}")

                if "authentication" in str(e).lower() or "401" in str(e):
                    raise LLMAuthError(f"Authentication failed: {e}")

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "LLM API error, retrying",
                        attempt=attempt + 1,
                        error=str(e),
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                raise LLMError(f"OpenAI API error: {e}")

        raise LLMError("Max retries exceeded")

    @property
    def total_token_usage(self) -> LLMTokenUsage:
        """获取累计 Token 使用量"""
        return self._token_usage


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude 客户端 — 原生 Messages API"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.llm.anthropic_api_key
        self.base_url = base_url or settings.llm.anthropic_base_url
        self.default_model = settings.llm.anthropic_model
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        self.timeout = settings.llm.timeout
        self.max_retries = settings.llm.max_retries
        self.retry_delay = settings.llm.retry_delay

        self._client = None
        self._client_init_lock = asyncio.Lock()
        self._token_usage = LLMTokenUsage()

        if not self.api_key:
            logger.warning("Anthropic API key not configured")

    async def _init_client(self):
        """初始化客户端（延迟初始化）"""
        if self._client is not None or not self.api_key:
            return

        async with self._client_init_lock:
            if self._client is not None:
                return
            try:
                from anthropic import AsyncAnthropic
                kwargs = {
                    "api_key": self.api_key,
                    "timeout": float(self.timeout),
                    "max_retries": 0,  # 我们自己处理重试
                }
                if self.base_url and self.base_url != "https://api.anthropic.com/v1":
                    kwargs["base_url"] = self.base_url
                self._client = AsyncAnthropic(**kwargs)
                logger.info("Anthropic client initialized")
            except ImportError:
                logger.warning("Anthropic package not installed")

    def count_tokens(self, text: str) -> int:
        """估算 Token 数量（简化版）"""
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.3 + other_chars * 0.25)

    @staticmethod
    def _convert_tools_to_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 OpenAI 格式的 tools 转换为 Anthropic 格式
        OpenAI:  {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        Anthropic: {"name": ..., "description": ..., "input_schema": ...}
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                # 如果已经是 Anthropic 格式或其他格式，直接传递
                anthropic_tools.append(tool)
        return anthropic_tools

    @staticmethod
    def _extract_system_and_messages(
        messages: List[LLMMessage],
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """
        从消息列表中提取 system 消息和用户/助手消息
        Claude API 要求 system 作为单独参数，messages 中只能有 user/assistant
        """
        system_parts = []
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role in ("user", "assistant"):
                api_messages.append({"role": msg.role, "content": msg.content})
            elif msg.role == "function":
                # function/tool result → 转换为 user 消息中的 tool_result block
                api_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.name or "unknown",
                            "content": msg.content,
                        }
                    ],
                })

        # 合并所有 system 消息
        system_text = "\n\n".join(system_parts) if system_parts else None

        # Claude 要求 messages 不能为空且必须以 user 开头
        if api_messages and api_messages[0]["role"] == "assistant":
            # 如果第一条是 assistant，在前面加一个空 user 消息
            api_messages.insert(0, {"role": "user", "content": "请继续。"})

        # Claude 不允许连续相同角色的消息，需要合并
        merged = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                # 合并连续同角色消息
                prev_content = merged[-1]["content"]
                curr_content = msg["content"]
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + "\n\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    merged[-1]["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    merged[-1]["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + [{"type": "text", "text": curr_content}]
            else:
                merged.append(msg)

        return system_text, merged

    async def chat_completion(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, str]] = None,
        **extra_kwargs,
    ) -> LLMResponse:
        """执行聊天补全，带自动重试"""
        start_time = time.perf_counter()

        await self._init_client()

        if self._client is None:
            raise LLMAuthError("OpenAI API key or package is not configured")

        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        openai_messages = [m.to_openai_format() for m in messages]

        for attempt in range(self.max_retries + 1):
            try:
                request_kwargs = {
                    "model": model,
                    "messages": openai_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                if system_text:
                    request_kwargs["system"] = system_text

                if tools:
                    request_kwargs["tools"] = self._convert_tools_to_anthropic(tools)
                    if tool_choice:
                        # 转换 tool_choice 格式
                        if isinstance(tool_choice, str):
                            if tool_choice == "auto":
                                request_kwargs["tool_choice"] = {"type": "auto"}
                            elif tool_choice == "none":
                                # Anthropic 没有 none，不传 tool_choice
                                pass
                            elif tool_choice == "required":
                                request_kwargs["tool_choice"] = {"type": "any"}
                            else:
                                request_kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}
                        elif isinstance(tool_choice, dict):
                            # 尝试直接传递
                            if "function" in tool_choice:
                                request_kwargs["tool_choice"] = {
                                    "type": "tool",
                                    "name": tool_choice["function"]["name"],
                                }
                            else:
                                request_kwargs["tool_choice"] = tool_choice

                response = await self._client.messages.create(**request_kwargs)

                latency = (time.perf_counter() - start_time) * 1000

                # 解析响应内容
                content_text = ""
                function_calls = []

                for block in response.content:
                    if block.type == "text":
                        content_text += block.text
                    elif block.type == "tool_use":
                        function_calls.append(LLMFunctionCall(
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                            raw_arguments=json.dumps(block.input, ensure_ascii=False) if block.input else "{}",
                        ))

                result = LLMResponse(
                    content=content_text if content_text else None,
                    function_calls=function_calls,
                    model=response.model,
                    provider=LLMProvider.ANTHROPIC,
                    latency_ms=latency,
                    raw_response=response,
                )

                # Token 使用
                if hasattr(response, "usage") and response.usage:
                    result.prompt_tokens = response.usage.input_tokens
                    result.completion_tokens = response.usage.output_tokens
                    result.total_tokens = response.usage.input_tokens + response.usage.output_tokens
                    self._token_usage.add(LLMTokenUsage(
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                    ))

                logger.debug(
                    "Anthropic chat completion",
                    model=model,
                    latency_ms=round(latency),
                    tokens=result.total_tokens,
                    has_function_call=result.has_function_call,
                )

                return result

            except Exception as e:
                error_str = str(e).lower()

                if "rate limit" in error_str or "429" in str(e):
                    if attempt < self.max_retries:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.warning(
                            "Anthropic rate limit hit, retrying",
                            attempt=attempt + 1,
                            delay_seconds=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise LLMRateLimitError(f"Anthropic rate limit exceeded after {self.max_retries} retries: {e}")

                if "authentication" in error_str or "401" in str(e) or "api_key" in error_str:
                    raise LLMAuthError(f"Anthropic authentication failed: {e}")

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "Anthropic API error, retrying",
                        attempt=attempt + 1,
                        error=str(e),
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                raise LLMError(f"Anthropic API error: {e}")

        raise LLMError("Max retries exceeded")

    @property
    def total_token_usage(self) -> LLMTokenUsage:
        """获取累计 Token 使用量"""
        return self._token_usage


class LLMClientFactory:
    """LLM 客户端工厂"""

    _instances: Dict[LLMProvider, BaseLLMClient] = {}
    _global_usage = LLMTokenUsage()

    @classmethod
    def get_client(cls, provider: LLMProvider = LLMProvider.OPENAI) -> BaseLLMClient:
        """获取 LLM 客户端实例"""
        if provider not in cls._instances:
            if provider == LLMProvider.OPENAI:
                # 检查是否需要使用星火配置
                active_provider = settings.llm.active_provider
                if active_provider in ("spark", "openai-spark"):
                    # 使用星火配置初始化 OpenAI 客户端
                    provider_config = settings.llm.get_provider_config(active_provider)
                    cls._instances[provider] = OpenAIClient(
                        api_key=provider_config.get("api_key"),
                        base_url=provider_config.get("base_url"),
                        model=provider_config.get("model_id"),
                    )
                    logger.info(f"OpenAI client initialized with Spark config: {provider_config.get('base_url')}, model: {provider_config.get('model_id')}")
                else:
                    cls._instances[provider] = OpenAIClient()
            elif provider == LLMProvider.ANTHROPIC:
                cls._instances[provider] = AnthropicClient()
            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")

        return cls._instances[provider]

    @classmethod
    def get_fallback_chain(cls) -> List[BaseLLMClient]:
        """获取 Fallback 客户端链"""
        clients = []
        
        # 首先根据 active_provider 获取主客户端
        active_provider = settings.llm.active_provider
        if active_provider in ("spark", "openai-spark"):
            # 星火使用 OpenAI 兼容格式
            try:
                clients.append(cls.get_client(LLMProvider.OPENAI))
            except Exception as e:
                logger.warning("Failed to create Spark client", error=str(e))
        else:
            # 使用 fallback_order 配置
            for provider_name in settings.llm.fallback_order:
                try:
                    provider = LLMProvider(provider_name)
                    clients.append(cls.get_client(provider))
                except (ValueError, Exception) as e:
                    logger.warning("Skipping fallback provider", provider=provider_name, error=str(e))
        return clients

    @classmethod
    def reset(cls) -> None:
        """重置所有客户端（测试用）"""
        cls._instances.clear()


class LLMService:
    """
    LLM 服务层
    提供带 Fallback、重试、错误处理的高级接口
    """

    def __init__(self):
        self._clients = LLMClientFactory.get_fallback_chain()
        self._logger = get_logger("llm_service")

    async def chat_completion(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        聊天补全，支持自动 Fallback
        """
        if not self._clients:
            raise LLMError("No LLM clients available")

        errors = []

        for i, client in enumerate(self._clients):
            try:
                if i > 0:
                    self._logger.info(
                        "Trying fallback provider",
                        provider=client.__class__.__name__,
                        previous_errors=len(errors),
                    )

                response = await client.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    response_format=response_format,
                    **kwargs,
                )

                if i > 0:
                    self._logger.info(
                        "Fallback provider succeeded",
                        provider=client.__class__.__name__,
                    )

                return response

            except (LLMRateLimitError, LLMAuthError) as e:
                # 这些错误应该尝试 Fallback
                errors.append(str(e))
                self._logger.warning(
                    "LLM provider failed, trying fallback",
                    provider=client.__class__.__name__,
                    error=str(e),
                )
                continue

            except Exception as e:
                # 其他错误也尝试 Fallback
                errors.append(str(e))
                self._logger.warning(
                    "Unexpected error with LLM provider, trying fallback",
                    provider=client.__class__.__name__,
                    error=str(e),
                )
                continue

        # 所有 Provider 都失败
        raise LLMError(f"All LLM providers failed: {'; '.join(errors)}")

    async def structured_output(
        self,
        messages: List[LLMMessage],
        output_schema: Dict[str, Any],
        temperature: float = 0.2,
        max_retries: int = 3,
        max_tokens: int = 8192,
    ) -> Dict[str, Any]:
        """
        结构化输出，确保返回符合 JSON Schema
        """
        # 添加 Schema 要求到系统消息
        schema_prompt = f"""
请严格按照以下 JSON Schema 格式输出结果，不要添加任何其他解释文字，直接输出 JSON：

{json.dumps(output_schema, indent=2, ensure_ascii=False)}

重要：输出必须是一个有效的 JSON 对象，不要用 markdown 代码块包裹，直接输出 JSON。
"""

        # 查找或创建系统消息
        has_system_message = any(m.role == "system" for m in messages)
        if has_system_message:
            request_messages = [
                LLMMessage(
                    role=msg.role,
                    content=msg.content + "\n\n" + schema_prompt,
                    name=msg.name,
                    function_call=msg.function_call,
                ) if msg.role == "system" else msg
                for msg in messages
            ]
        else:
            request_messages = [LLMMessage(role="system", content=schema_prompt), *messages]

        for attempt in range(max_retries):
            try:
                response = await self.chat_completion(
                    messages=request_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )

                if not response.content:
                    raise ValueError("Empty response from LLM")

                # 尝试解析 JSON
                content = response.content.strip()

                # 尝试多种提取方式
                import re

                # 方式1：从 Markdown 代码块中提取
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

                # 方式2：直接尝试解析整个内容
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass

                # 方式3：查找第一个 { 和最后一个 } 之间的内容
                brace_start = content.find('{')
                brace_end = content.rfind('}')
                if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                    try:
                        return json.loads(content[brace_start:brace_end + 1])
                    except json.JSONDecodeError:
                        pass

                raise json.JSONDecodeError("No valid JSON found in response", content, 0)

            except (json.JSONDecodeError, ValueError) as e:
                if attempt < max_retries - 1:
                    self._logger.warning(
                        "Failed to parse JSON, retrying",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    # 给 LLM 反馈错误
                    request_messages = [
                        *request_messages,
                        LLMMessage(
                            role="user",
                            content=f"之前的输出不是有效的 JSON。错误: {e}。请直接输出 JSON 对象，不要有任何其他文字、代码块标记或解释。",
                        ),
                    ]
                    await asyncio.sleep(0.5)
                    continue
                raise LLMError(f"Failed to parse structured output after {max_retries} attempts: {e}")

        raise LLMError("Max retries exceeded for structured output")


# 全局服务实例
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """获取全局 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
