"""
对比分析发明与多篇现有技术的技术特征差异
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)


class PriorArtComparatorTool(HermesTool):
    """对比分析发明与多篇现有技术的技术特征差异"""
    name = "prior_art_comparator"
    description = "对比分析发明与多篇现有技术的技术特征差异"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "invention": HermesToolParameter(
                    type="string",
                    description="发明技术方案描述",
                    required=True,
                ),
                "prior_arts": HermesToolParameter(
                    type="string",
                    description="现有技术列表",
                    required=True,
                ),
            },
        )

    async def execute(self,     invention: str,     prior_arts: str, **kwargs) -> Dict[str, Any]:
        """执行工具逻辑"""
        logger.info("Executing tool", tool=self.name)
        llm = get_llm_service()
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=f"对比分析发明与多篇现有技术的技术特征差异")],
            temperature=0.3,
        )
        return {"result": response.content, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("prior_art_comparator", PriorArtComparatorTool)
