"""
IPC Classifier Tool - IPC 分类工具
帮助需求分析 Agent 对技术方案进行 IPC 国际专利分类
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

IPC_PROMPT = """你是一位专利分类专家。请根据以下技术描述，给出最可能的 IPC 国际专利分类号。

技术描述：
{tech_description}

请输出 JSON 格式：
{{
  "primary_ipc": "主分类号（如 G06F 18/24）",
  "secondary_ipc": ["次要分类号1", "次要分类号2"],
  "reasoning": "分类理由说明",
  "confidence": 0.85
}}"""


class IPCClassifierTool(HermesTool):
    """IPC 国际专利分类工具"""
    name = "ipc_classifier"
    description = "根据技术描述进行 IPC 国际专利分类，返回主分类号和次要分类号"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术发明描述文本",
                    required=True,
                ),
            },
        )

    async def execute(self, tech_description: str, **kwargs) -> Dict[str, Any]:
        """执行 IPC 分类"""
        logger.info("Classifying technology into IPC categories")
        llm = get_llm_service()
        prompt = IPC_PROMPT.format(tech_description=tech_description)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"ipc_classification": response.content, "tool": self.name}
