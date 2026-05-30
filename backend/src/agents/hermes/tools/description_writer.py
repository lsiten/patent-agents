"""
Description Writer Tool - 说明书撰写工具
帮助撰写专利说明书各章节
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

DESCRIPTION_PROMPT = """你是一位资深专利代理人。请撰写专利说明书的"{section_type}"部分。

技术内容：
{technical_content}

相关权利要求：
{claims}

撰写要求：
- 内容公开充分，使本领域技术人员能够实施
- 与权利要求书对应，提供充分支持
- 使用规范专利术语
- 逻辑清晰，层次分明

请直接输出该章节的正文内容。"""


class DescriptionWriterTool(HermesTool):
    """说明书撰写工具"""
    name = "description_writer"
    description = "撰写专利说明书各章节（技术领域、背景技术、发明内容、具体实施方式等）"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "section_type": HermesToolParameter(
                    type="string",
                    description="章节类型: technical_field/background/summary/drawings/detailed",
                    required=True,
                    enum=["technical_field", "background", "summary", "drawings", "detailed"],
                ),
                "technical_content": HermesToolParameter(
                    type="string",
                    description="该章节涉及的技术内容",
                    required=True,
                ),
                "claims": HermesToolParameter(
                    type="string",
                    description="相关权利要求（用于确保支持性）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, section_type: str, technical_content: str, claims: str = "", **kwargs
    ) -> Dict[str, Any]:
        """执行说明书章节撰写"""
        logger.info("Writing patent description section", section=section_type)
        llm = get_llm_service()
        prompt = DESCRIPTION_PROMPT.format(
            section_type=section_type,
            technical_content=technical_content,
            claims=claims or "未提供",
        )
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.4,
        )
        return {"description_section": response.content, "section_type": section_type, "tool": self.name}


def register(factory) -> None:
    factory.register_tool_class("description_writer", DescriptionWriterTool)
