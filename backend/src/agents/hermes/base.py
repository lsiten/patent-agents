"""
Hermes Agent 底座 - 基于 NousResearch Hermes Agent 架构
提供函数调用、工具集成、结构化输出、子Agent孵化等核心能力
"""
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from src.core.config import settings
from src.core.logging import get_logger
from src.core.llm_client import (
    get_llm_service,
    LLMMessage as CoreLLMMessage,
    LLMResponse,
    LLMFunctionCall as CoreLLMFunctionCall,
)

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class HermesFunctionCall(BaseModel):
    """Hermes 函数调用模型"""
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    id: str = Field(default_factory=lambda: str(uuid4()))


class HermesFunctionResult(BaseModel):
    """Hermes 函数执行结果"""
    name: str
    call_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result: Any
    success: bool = True
    error: Optional[str] = None


class HermesMessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION_CALL = "function_call"
    FUNCTION_RESULT = "function_result"
    TOOL = "tool"


class HermesMessage(BaseModel):
    """Hermes 消息模型"""
    role: HermesMessageRole
    content: Optional[str] = None
    name: Optional[str] = None  # 用于工具/函数名称
    function_call: Optional[HermesFunctionCall] = None
    tool_calls: Optional[List[HermesFunctionCall]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI API 格式"""
        msg = {"role": self.role.value}
        if self.content:
            msg["content"] = self.content
        if self.name:
            msg["name"] = self.name
        if self.function_call:
            msg["function_call"] = {
                "name": self.function_call.name,
                "arguments": json.dumps(self.function_call.parameters, ensure_ascii=False)
            }
        return msg


class HermesToolParameter(BaseModel):
    """工具参数定义"""
    type: str = "string"
    description: str = ""
    enum: Optional[List[Any]] = None
    required: bool = True


class HermesToolDefinition(BaseModel):
    """Hermes 工具定义"""
    name: str
    description: str
    parameters: Dict[str, HermesToolParameter] = Field(default_factory=dict)
    return_type: str = "string"

    def to_openai_function(self) -> Dict[str, Any]:
        """转换为 OpenAI Function 格式"""
        required = [
            name for name, param in self.parameters.items()
            if param.required
        ]
        properties = {
            name: {
                "type": param.type,
                "description": param.description,
            }
            for name, param in self.parameters.items()
        }
        # 添加 enum 如果存在
        for name, param in self.parameters.items():
            if param.enum:
                properties[name]["enum"] = param.enum

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class HermesTool:
    """Hermes 工具基类"""
    name: str
    description: str

    def __init__(self):
        self._definition: Optional[HermesToolDefinition] = None
        self._handler: Optional[Callable] = None

    @property
    def definition(self) -> HermesToolDefinition:
        """获取工具定义"""
        if not self._definition:
            self._definition = self._build_definition()
        return self._definition

    def _build_definition(self) -> HermesToolDefinition:
        """构建工具定义 - 子类实现"""
        raise NotImplementedError

    async def execute(self, **kwargs) -> Any:
        """执行工具 - 子类实现"""
        raise NotImplementedError

    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI 工具格式"""
        return self.definition.to_openai_function()


@dataclass
class HermesAgentContext:
    """Hermes Agent 上下文"""
    agent_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = field(default_factory=lambda: str(uuid4()))
    parent_agent_id: Optional[str] = None
    conversation_history: List[HermesMessage] = field(default_factory=list)
    tool_results: List[HermesFunctionResult] = field(default_factory=list)
    max_function_calls: int = 10
    current_function_calls: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: HermesMessage) -> None:
        """添加消息到历史"""
        self.conversation_history.append(message)

    def add_tool_result(self, result: HermesFunctionResult) -> None:
        """添加工具执行结果"""
        self.tool_results.append(result)
        self.current_function_calls += 1

    def should_stop(self) -> bool:
        """判断是否应该停止工具调用"""
        return self.current_function_calls >= self.max_function_calls

    def get_conversation_for_llm(self) -> List[Dict[str, Any]]:
        """获取用于 LLM 的对话历史"""
        return [msg.to_openai_format() for msg in self.conversation_history]


class HermesAgent(ABC):
    """
    Hermes Agent 基类
    提供:
    - 系统提示词管理
    - 工具注册与调用
    - 结构化输出解析
    - 子 Agent 孵化
    - 思考过程追踪
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_iterations: int = 10,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.model = model or settings.llm.llm_model
        self.temperature = temperature
        self.max_iterations = max_iterations

        self._tools: Dict[str, HermesTool] = {}
        self._context: Optional[HermesAgentContext] = None

        # 注册默认工具
        self._register_default_tools()

    @property
    def context(self) -> HermesAgentContext:
        """获取当前上下文"""
        if not self._context:
            self._context = HermesAgentContext()
        return self._context

    def register_tool(self, tool: HermesTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        logger.debug("Registered tool", agent=self.name, tool=tool.name)

    def register_tools(self, tools: List[HermesTool]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register_tool(tool)

    def _register_default_tools(self) -> None:
        """注册默认工具"""
        # 可以在这里注册通用工具
        pass

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI 格式定义"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    async def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Type[T]] = None,
    ) -> Union[str, T, Dict[str, Any]]:
        """
        运行 Agent

        Args:
            user_input: 用户输入
            context: 额外上下文
            output_schema: 期望的输出 Pydantic 模型（结构化输出）

        Returns:
            Agent 执行结果
        """
        logger.info("Agent starting", agent=self.name, input_length=len(user_input))

        # 初始化上下文
        self._context = HermesAgentContext(
            metadata=context or {},
            max_function_calls=self.max_iterations,
        )

        # 添加系统提示词
        self.context.add_message(HermesMessage(
            role=HermesMessageRole.SYSTEM,
            content=self._build_system_prompt(output_schema),
        ))

        # 添加用户输入
        self.context.add_message(HermesMessage(
            role=HermesMessageRole.USER,
            content=user_input,
        ))

        # 主循环 - 思考-行动循环
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 1. 思考阶段 - 调用 LLM
            response = await self._call_llm()

            # 2. 解析响应
            function_calls = self._parse_function_calls(response)

            # 3. 如果没有函数调用，直接返回结果
            if not function_calls:
                result = self._clean_tool_call_tags(response.content or "")
                if output_schema:
                    return self._parse_structured_output(result, output_schema)
                return result

            # 4. 执行函数调用
            for func_call in function_calls:
                result = await self._execute_tool_call(func_call)

                # 记录工具调用结果到上下文
                self.context.add_tool_result(result)

                # 将函数调用和结果添加到对话历史
                self.context.add_message(HermesMessage(
                    role=HermesMessageRole.ASSISTANT,
                    function_call=func_call,
                ))

                self.context.add_message(HermesMessage(
                    role=HermesMessageRole.FUNCTION_RESULT,
                    name=func_call.name,
                    content=json.dumps(result.result, ensure_ascii=False) if result.success else result.error,
                ))

            # 检查是否应该停止
            if self.context.should_stop():
                logger.warning("Agent reached max function calls", agent=self.name)
                break

        # 最终响应
        final_response = await self._call_llm()
        final_content = self._clean_tool_call_tags(final_response.content or "")

        if output_schema:
            return self._parse_structured_output(final_content, output_schema)

        return final_content

    async def run_stream(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        流式运行 Agent — async generator，逐步 yield 事件

        事件格式: {"type": str, "data": dict}
        事件类型:
          - thinking: Agent 开始思考
          - skill_use: Agent 使用技能
          - tool_call_start: 开始调用工具
          - tool_call_end: 工具调用完成
          - content: 最终回复内容
          - done: 执行完成
        """
        logger.info("Agent stream starting", agent=self.name, input_length=len(user_input))

        # 初始化上下文
        self._context = HermesAgentContext(
            metadata=context or {},
            max_function_calls=self.max_iterations,
        )

        # 添加系统提示词
        self.context.add_message(HermesMessage(
            role=HermesMessageRole.SYSTEM,
            content=self._build_system_prompt(None),
        ))

        # 添加用户输入
        self.context.add_message(HermesMessage(
            role=HermesMessageRole.USER,
            content=user_input,
        ))

        # 主循环
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 1. 思考阶段
            yield {"type": "thinking", "data": {"iteration": iteration, "agent": self.name}}

            response = await self._call_llm()

            # 2. 解析技能使用
            skill_uses = self._parse_skill_uses(response.content or "")
            for skill in skill_uses:
                yield {"type": "skill_use", "data": skill}

            # 3. 解析工具调用
            function_calls = self._parse_function_calls(response)

            # 4. 如果没有函数调用，返回最终结果
            if not function_calls:
                final_content = self._clean_tool_call_tags(response.content or "")
                final_content = self._clean_skill_use_tags(final_content)
                yield {"type": "content", "data": {"content": final_content}}
                yield {"type": "done", "data": {"iterations": iteration, "tool_calls_count": len(self.context.tool_results)}}
                return

            # 5. 执行工具调用
            for func_call in function_calls:
                yield {"type": "tool_call_start", "data": {"name": func_call.name, "parameters": func_call.parameters}}

                result = await self._execute_tool_call(func_call)
                self.context.add_tool_result(result)

                yield {"type": "tool_call_end", "data": {
                    "name": result.name,
                    "parameters": result.parameters,
                    "result": result.result if result.success else None,
                    "success": result.success,
                    "error": result.error,
                }}

                # 添加到对话历史
                self.context.add_message(HermesMessage(
                    role=HermesMessageRole.ASSISTANT,
                    function_call=func_call,
                ))
                self.context.add_message(HermesMessage(
                    role=HermesMessageRole.FUNCTION_RESULT,
                    name=func_call.name,
                    content=json.dumps(result.result, ensure_ascii=False) if result.success else result.error,
                ))

            if self.context.should_stop():
                logger.warning("Agent reached max function calls", agent=self.name)
                break

        # 最终响应
        yield {"type": "thinking", "data": {"iteration": iteration + 1, "agent": self.name, "phase": "final"}}
        final_response = await self._call_llm()
        final_content = self._clean_tool_call_tags(final_response.content or "")
        final_content = self._clean_skill_use_tags(final_content)

        # 解析最终回复中的技能使用
        skill_uses = self._parse_skill_uses(final_response.content or "")
        for skill in skill_uses:
            yield {"type": "skill_use", "data": skill}

        yield {"type": "content", "data": {"content": final_content}}
        yield {"type": "done", "data": {"iterations": iteration, "tool_calls_count": len(self.context.tool_results)}}

    def _build_system_prompt(self, output_schema: Optional[Type[T]] = None) -> str:
        """构建系统提示词 — 包含 Hermes 风格的工具调用指令"""
        prompt = self.system_prompt

        # 添加工具/技能调用说明（Hermes prompt-based function calling）
        if self._tools:
            tool_schemas = []
            for name, tool in self._tools.items():
                tool_def = tool.definition
                params_schema = {}
                for p_name, p_def in tool_def.parameters.items():
                    params_schema[p_name] = {
                        "type": p_def.type,
                        "description": p_def.description,
                    }
                    if p_def.enum:
                        params_schema[p_name]["enum"] = p_def.enum

                tool_schemas.append({
                    "name": name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": params_schema,
                        "required": [p for p, d in tool_def.parameters.items() if d.required],
                    },
                })

            tools_json = json.dumps(tool_schemas, indent=2, ensure_ascii=False)
            prompt += f"""

## 可用工具/技能

你可以调用以下工具来辅助分析。当你需要使用工具时，请在回复中使用以下格式：

<tool_call>
{{"name": "工具名称", "arguments": {{"参数名": "参数值"}}}}
</tool_call>

你可以在一次回复中调用多个工具。工具调用后系统会返回结果，你再基于结果继续回答。

可用工具列表：
{tools_json}

重要：只在确实需要时才调用工具。如果你能直接回答用户问题，就直接回答。"""

        # 添加技能使用标记说明
        prompt += """

## 技能使用声明

当你在回复中运用了某项专业技能时，请用以下标记声明：

<skill_use>
{"name": "技能名称", "description": "技能说明", "reasoning": "为什么使用该技能"}
</skill_use>

可声明的技能包括：创意激发、技术分析、风险评估、保护方向探索、IPC分类、专利性判断、现有技术对比、商业价值分析、权利要求设计、Agent调度。
你可以在回复中声明多个技能的使用。"""

        # 添加结构化输出要求
        if output_schema:
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2, ensure_ascii=False)
            prompt += f"\n\n请严格按照以下 JSON Schema 格式输出结果:\n{schema_json}"

        return prompt

    async def _call_llm(self) -> LLMResponse:
        """调用 LLM API - 不传 tools 参数，使用 prompt-based tool calling"""
        try:
            llm_service = get_llm_service()

            # 将 HermesMessage 转换为 LLMMessage
            messages = []
            for msg in self.context.conversation_history:
                if msg.role == HermesMessageRole.SYSTEM:
                    messages.append(CoreLLMMessage(role="system", content=msg.content or ""))
                elif msg.role == HermesMessageRole.USER:
                    messages.append(CoreLLMMessage(role="user", content=msg.content or ""))
                elif msg.role == HermesMessageRole.ASSISTANT:
                    messages.append(CoreLLMMessage(role="assistant", content=msg.content or ""))
                elif msg.role == HermesMessageRole.FUNCTION_RESULT or msg.role == HermesMessageRole.TOOL:
                    messages.append(CoreLLMMessage(role="user", content=f"[工具 {msg.name} 的执行结果]:\n{msg.content or ''}"))

            # 不传 tools 参数 — 工具调用通过 prompt 文本解析
            return await llm_service.chat_completion(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
            )
        except Exception as e:
            logger.error(f"[HermesAgent._call_llm] LLM调用失败: {e}")
            raise

    def _parse_function_calls(self, response: LLMResponse) -> List[HermesFunctionCall]:
        """解析 LLM 响应中的函数调用 — 支持 API tool_calls 和 prompt-based <tool_call> 标记"""
        calls = []

        # 方式1：API 原生 tool_calls（proxy 支持时）
        if response.has_function_call:
            for func_call in response.function_calls:
                calls.append(HermesFunctionCall(
                    name=func_call.name,
                    parameters=func_call.arguments,
                    id=str(uuid4()),
                ))
            return calls

        # 方式2：从文本中解析 <tool_call> 标记（Hermes prompt-based）
        content = response.content or ""
        tool_call_pattern = re.compile(
            r'<tool_call>\s*(\{.*?\})\s*</tool_call>',
            re.DOTALL,
        )

        for match in tool_call_pattern.finditer(content):
            try:
                call_data = json.loads(match.group(1))
                name = call_data.get("name", "")
                arguments = call_data.get("arguments", {})
                if name and name in self._tools:
                    calls.append(HermesFunctionCall(
                        name=name,
                        parameters=arguments if isinstance(arguments, dict) else {},
                        id=str(uuid4()),
                    ))
                    logger.info(f"Parsed prompt-based tool call: {name}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse tool_call: {e}, raw: {match.group(1)[:100]}")

        return calls

    @staticmethod
    def _clean_tool_call_tags(content: str) -> str:
        """清理响应文本中的 <tool_call> 标记"""
        cleaned = re.sub(r'<tool_call>\s*\{.*?\}\s*</tool_call>', '', content, flags=re.DOTALL)
        # 清理多余空行
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    @staticmethod
    def _parse_skill_uses(content: str) -> List[Dict[str, Any]]:
        """解析响应文本中的 <skill_use> 标记"""
        skill_uses = []
        pattern = re.compile(r'<skill_use>\s*(\{.*?\})\s*</skill_use>', re.DOTALL)
        for match in pattern.finditer(content):
            try:
                data = json.loads(match.group(1))
                skill_uses.append({
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "reasoning": data.get("reasoning", ""),
                })
            except (json.JSONDecodeError, KeyError):
                pass
        return skill_uses

    @staticmethod
    def _clean_skill_use_tags(content: str) -> str:
        """清理响应文本中的 <skill_use> 标记"""
        cleaned = re.sub(r'<skill_use>\s*\{.*?\}\s*</skill_use>', '', content, flags=re.DOTALL)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    async def _execute_tool_call(self, func_call: HermesFunctionCall) -> HermesFunctionResult:
        """执行工具调用"""
        logger.info(
            "Executing tool call",
            agent=self.name,
            tool=func_call.name,
            params=list(func_call.parameters.keys()),
        )

        tool = self._tools.get(func_call.name)
        if not tool:
            error_msg = f"Tool not found: {func_call.name}"
            logger.error(error_msg)
            return HermesFunctionResult(
                name=func_call.name,
                call_id=func_call.id,
                parameters=func_call.parameters,
                result=None,
                success=False,
                error=error_msg,
            )

        try:
            result = await tool.execute(**func_call.parameters)
            logger.info(
                "Tool executed successfully",
                agent=self.name,
                tool=func_call.name,
            )
            return HermesFunctionResult(
                name=func_call.name,
                call_id=func_call.id,
                parameters=func_call.parameters,
                result=result,
                success=True,
            )
        except Exception as e:
            logger.error(
                "Tool execution failed",
                agent=self.name,
                tool=func_call.name,
                error=str(e),
                exc_info=True,
            )
            return HermesFunctionResult(
                name=func_call.name,
                call_id=func_call.id,
                parameters=func_call.parameters,
                result=None,
                success=False,
                error=str(e),
            )

    def _parse_structured_output(self, content: str, schema: Type[T]) -> T:
        """解析结构化输出"""
        # 尝试从 Markdown 代码块中提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            content = json_match.group(1)

        try:
            data = json.loads(content)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(
                "Failed to parse structured output, returning raw",
                error=str(e),
            )
            # 降级：尝试创建一个包含原始内容的对象
            return schema.model_construct(**{"raw_content": content})

    def spawn_child_agent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: Optional[List[HermesTool]] = None,
    ) -> "HermesAgent":
        """
        孵化子 Agent - Hermes 核心能力
        允许 Agent 创建专门的子 Agent 处理特定任务
        """
        child = HermesAgent(
            name=f"{self.name}/{name}",
            description=description,
            system_prompt=system_prompt,
            model=self.model,
            temperature=self.temperature,
        )

        # 继承父 Agent 的 LLM 服务
        if self._llm_service:
            child.set_llm_service(self._llm_service)

        # 注册工具
        if tools:
            child.register_tools(tools)

        logger.info(
            "Spawned child agent",
            parent=self.name,
            child=child.name,
        )

        return child


class HermesAgentCoordinator:
    """
    Hermes Agent 协调器 - CEO Agent 模式
    统筹多个专业 Agent 的协同工作
    """

    def __init__(self, name: str = "Coordinator"):
        self.name = name
        self._agents: Dict[str, HermesAgent] = {}
        self._logger = get_logger("coordinator")

    def register_agent(self, agent: HermesAgent) -> None:
        """注册专业 Agent"""
        self._agents[agent.name] = agent
        self._logger.info(
            "Registered specialist agent",
            coordinator=self.name,
            agent=agent.name,
        )

    def register_agents(self, agents: List[HermesAgent]) -> None:
        """批量注册 Agent"""
        for agent in agents:
            self.register_agent(agent)

    async def orchestrate(
        self,
        task: str,
        workflow: List[str],  # 按顺序执行的 Agent 名称列表
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        编排多 Agent 工作流

        Args:
            task: 总体任务描述
            workflow: Agent 执行顺序（名称列表）
            context: 初始上下文

        Returns:
            最终结果汇总
        """
        self._logger.info(
            "Starting agent orchestration",
            coordinator=self.name,
            task_length=len(task),
            workflow=workflow,
        )

        results: Dict[str, Any] = {}
        current_context = context or {}

        for agent_name in workflow:
            if agent_name not in self._agents:
                self._logger.warning("Agent not found, skipping", agent=agent_name)
                continue

            agent = self._agents[agent_name]
            self._logger.info("Running agent in workflow", agent=agent_name)

            # 构建 Agent 输入，包含之前的结果
            enhanced_input = self._build_agent_input(
                task=task,
                agent_name=agent_name,
                previous_results=results,
                current_context=current_context,
            )

            try:
                result = await agent.run(enhanced_input)
                results[agent_name] = result
                current_context[f"{agent_name}_result"] = result

                self._logger.info(
                    "Agent completed successfully",
                    agent=agent_name,
                )

            except Exception as e:
                self._logger.error(
                    "Agent failed in workflow",
                    agent=agent_name,
                    error=str(e),
                    exc_info=True,
                )
                results[agent_name] = {"error": str(e)}

        self._logger.info("Orchestration completed", total_agents=len(results))

        return {
            "task": task,
            "results": results,
            "workflow_completed": True,
        }

    def _build_agent_input(
        self,
        task: str,
        agent_name: str,
        previous_results: Dict[str, Any],
        current_context: Dict[str, Any],
    ) -> str:
        """构建 Agent 输入"""
        input_parts = [f"总体任务: {task}\n"]
        input_parts.append(f"当前角色: {agent_name}\n")

        if previous_results:
            input_parts.append("\n之前步骤的结果:")
            for name, result in previous_results.items():
                input_parts.append(f"\n【{name}】:\n{result}\n")

        if current_context:
            input_parts.append("\n上下文信息:")
            for key, value in current_context.items():
                if not key.endswith("_result"):
                    input_parts.append(f"- {key}: {value}")

        return "\n".join(input_parts)
