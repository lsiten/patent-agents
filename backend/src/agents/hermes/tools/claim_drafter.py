"""
Claim Drafter Tool - 权利要求撰写工具
帮助专利撰写 Agent 生成高质量权利要求书
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

CLAIM_PROMPT = """你是一位资深专利代理人。请根据以下技术特征和保护范围要求，撰写权利要求书。

技术特征：
{features}

保护范围要求：
{protection_scope}

撰写要求：
1. 独立权利要求应概括保护范围，使用上位概念
2. 从属权利要求逐步限缩，体现技术细节
3. 语言规范、清楚、简要
4. 引用关系正确

请输出 JSON 格式：
{{
  "independent_claim": "独立权利要求1全文",
  "dependent_claims": ["从属权利要求2", "从属权利要求3"],
  "claim_tree": {{
    "1": [],
    "2": ["1"],
    "3": ["1"]
  }},
  "protection_breadth": "保护范围评估",
  "drafting_notes": "撰写说明"
}}"""


class ClaimDrafterTool(HermesTool):
    """权利要求撰写工具"""
    name = "claim_drafter"
    description = "根据技术特征撰写独立权利要求和从属权利要求"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "features": HermesToolParameter(
                    type="string",
                    description="技术特征列表或描述",
                    required=True,
                ),
                "protection_scope": HermesToolParameter(
                    type="string",
                    description="期望的保护范围说明",
                    required=False,
                ),
            },
        )

    async def execute(
        self, features: str, protection_scope: str = "尽可能宽泛", **kwargs
    ) -> Dict[str, Any]:
        """执行权利要求撰写"""
        logger.info("Drafting patent claims")
        llm = get_llm_service()
        prompt = CLAIM_PROMPT.format(features=features, protection_scope=protection_scope)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.4,
        )
        return {"claims_draft": response.content, "tool": self.name}
