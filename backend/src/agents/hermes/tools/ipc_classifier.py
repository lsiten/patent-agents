"""
IPC Classifier Tool - IPC 分类工具
帮助需求分析 Agent 对技术方案进行 IPC 国际专利分类
"""
import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
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


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON"""
    import re
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取代码块中的 JSON
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 尝试提取 { } 之间的内容
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


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
        start_time = datetime.now()
        logger.info("Classifying technology into IPC categories")
        
        try:
            llm = get_llm_service()
            prompt = IPC_PROMPT.format(tech_description=tech_description)
            response = await llm.chat_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
            )
            
            # 解析 LLM 响应
            parsed = _extract_json_from_response(response.content)
            
            # 构造标准化输出数据
            data = {
                "primary_code": parsed.get("primary_ipc", ""),
                "secondary_codes": parsed.get("secondary_ipc", []),
                "classification_rationale": parsed.get("reasoning", ""),
                "confidence": parsed.get("confidence", 0.0),
            }
            
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=response.content,
                start_time=start_time,
            )
            
        except Exception as e:
            logger.error(f"IPC classification failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
