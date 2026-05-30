"""
Hermes 工具基类定义
保留 HermesTool / HermesToolDefinition / HermesToolParameter 供 21 个工具实现使用。
旧的 HermesAgent / HermesAgentContext 等已移除（由 run_agent.AIAgent 替代）。
"""
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


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
