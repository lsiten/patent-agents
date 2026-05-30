"""
OA Predictor Tool - 审查意见预测工具
预测专利审查过程中可能收到的审查意见
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.core.llm_client import get_llm_service, LLMMessage

logger = get_logger(__name__)

OA_PROMPT = """你是一位经验丰富的专利审查员。请预测以下专利申请在审查过程中可能收到的审查意见。

专利文件摘要：
{patent_document}

请考虑：
1. 新颖性驳回（A22.2）
2. 创造性驳回（A22.3）
3. 说明书公开不充分（A26.3）
4. 权利要求不清楚（A26.4）
5. 修改超范围（A33）

请输出 JSON 格式：
{{
  "predicted_objections": [
    {{
      "type": "novelty/inventive_step/sufficiency/clarity/amendment",
      "likelihood": "high/medium/low",
      "legal_basis": "法律条文依据",
      "description": "预测的审查意见内容",
      "affected_claims": [1, 2],
      "mitigation": "应对策略建议"
    }}
  ],
  "overall_risk": "high/medium/low",
  "proactive_suggestions": ["主动修改建议1", "主动修改建议2"]
}}"""


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


class OAPredictorTool(HermesTool):
    """审查意见预测工具"""
    name = "oa_predictor"
    description = "预测专利审查中可能收到的审查意见，提供应对策略"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "patent_document": HermesToolParameter(
                    type="string",
                    description="专利申请文件内容（权利要求+说明书摘要）",
                    required=True,
                ),
            },
        )

    async def execute(self, patent_document: str, **kwargs) -> Dict[str, Any]:
        """执行审查意见预测"""
        start_time = datetime.now()
        logger.info("Predicting office action objections")
        
        try:
            llm = get_llm_service()
            prompt = OA_PROMPT.format(patent_document=patent_document)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.3,
            )
            
            parsed = _extract_json_from_response(response.content)
            
            # 标准化输出数据
            data = {
                "predicted_objections": parsed.get("predicted_objections", []),
                "overall_risk": parsed.get("overall_risk", "unknown"),
                "risk_level": parsed.get("overall_risk", "unknown"),  # 别名字段
                "proactive_suggestions": parsed.get("proactive_suggestions", []),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"OA prediction failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
