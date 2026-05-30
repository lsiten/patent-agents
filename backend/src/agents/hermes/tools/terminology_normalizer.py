"""
Terminology Normalizer Tool - 术语规范化工具
规范专利文件中的技术术语使用
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

NORMALIZE_PROMPT = """你是一位专利术语规范化专家。请检查以下文本中的技术术语使用，确保一致性和规范性。

文本内容：
{text}

技术领域：{domain}

请输出 JSON 格式：
{{
  "normalized_text": "规范化后的文本",
  "term_mappings": [
    {{
      "original": "原始用词",
      "normalized": "规范用词",
      "reason": "修改原因"
    }}
  ],
  "consistency_issues": ["一致性问题1"],
  "key_terms_glossary": {{
    "术语1": "定义1"
  }}
}}"""


class TerminologyNormalizerTool(HermesTool):
    """术语规范化工具"""
    name = "terminology_normalizer"
    description = "规范专利文件中的技术术语，确保全文一致性和专业性"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "text": HermesToolParameter(
                    type="string",
                    description="需要规范化的文本",
                    required=True,
                ),
                "domain": HermesToolParameter(
                    type="string",
                    description="技术领域（如：人工智能、机械工程）",
                    required=False,
                ),
            },
        )

    async def execute(self, text: str, domain: str = "通用技术", **kwargs) -> Dict[str, Any]:
        """执行术语规范化"""
        logger.info("Normalizing terminology", domain=domain)
        llm = get_llm_service()
        prompt = NORMALIZE_PROMPT.format(text=text, domain=domain)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"normalization_result": response.content, "tool": self.name}
