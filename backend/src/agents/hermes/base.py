"""
Hermes 工具基类定义
保留 HermesTool / HermesToolDefinition / HermesToolParameter 供 21 个工具实现使用。
旧的 HermesAgent / HermesAgentContext 等已移除（由 run_agent.AIAgent 替代）。
"""
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# ============ 标准工具输出结构 ============

class ToolOutputSchema(TypedDict, total=False):
    """标准工具输出格式 - 所有工具应返回符合此结构的字典
    
    必需字段:
        tool: 工具名称
        success: 是否执行成功
        data: 工具特定的输出数据
        
    可选字段:
        timestamp: 执行时间 (ISO 8601)
        duration_ms: 执行耗时（毫秒）
        error: 错误信息（失败时）
        raw_response: 原始响应（调试用）
    """
    tool: str
    success: bool
    data: Dict[str, Any]
    timestamp: str
    duration_ms: float
    error: str
    raw_response: str


def make_tool_output(
    tool_name: str,
    data: Dict[str, Any],
    success: bool = True,
    error: Optional[str] = None,
    raw_response: Optional[str] = None,
    start_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """创建标准工具输出的辅助函数
    
    Args:
        tool_name: 工具名称
        data: 工具特定的输出数据
        success: 是否执行成功
        error: 错误信息（失败时）
        raw_response: 原始响应（调试用）
        start_time: 开始执行时间（用于计算 duration_ms）
        
    Returns:
        符合 ToolOutputSchema 的字典
    """
    now = datetime.now()
    result: Dict[str, Any] = {
        "tool": tool_name,
        "success": success,
        "data": data,
        "timestamp": now.isoformat(),
    }
    
    if start_time:
        result["duration_ms"] = (now - start_time).total_seconds() * 1000
    
    if error:
        result["error"] = error
        
    if raw_response:
        result["raw_response"] = raw_response
        
    return result


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
