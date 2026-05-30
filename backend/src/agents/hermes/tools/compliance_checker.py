"""
Compliance Checker Tool - 形式合规检查工具
检查专利文件的格式和形式合规性
"""
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

COMPLIANCE_PROMPT = """你是一位专利形式审查专家。请检查以下专利文件的形式合规性。

专利文件内容：
{patent_document}

检查项目包括：
1. 格式规范（编号、标点、段落）
2. 术语一致性
3. 引用关系正确性
4. 必要组成部分完整性
5. 附图标记对应关系

请输出 JSON 格式：
{{
  "compliance_issues": [
    {{
      "severity": "critical/high/medium/low",
      "location": "问题位置",
      "issue": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "overall_compliance": "pass/conditional_pass/fail",
  "score": 85,
  "summary": "形式审查总结"
}}"""


class ComplianceCheckerTool(HermesTool):
    """形式合规检查工具"""
    name = "compliance_checker"
    description = "检查专利申请文件的格式和形式合规性，识别格式问题"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "patent_document": HermesToolParameter(
                    type="string",
                    description="专利文件内容（全文或指定部分）",
                    required=True,
                ),
            },
        )

    async def execute(self, patent_document: str, **kwargs) -> Dict[str, Any]:
        """执行形式合规检查"""
        logger.info("Checking formal compliance")
        llm = get_llm_service()
        prompt = COMPLIANCE_PROMPT.format(patent_document=patent_document)
        response = await llm.chat_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.2,
        )
        return {"compliance_result": response.content, "tool": self.name}
