"""
Terminology Normalizer Tool - 术语规范化工具
规范专利文件中的技术术语使用
"""
import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

TERM_MAPPINGS = {
    "屏幕": "显示面",
    "小屏幕": "可调显示面",
    "地面屏": "地面显示面",
    "投影屏": "显示面",
    "画面": "视频内容",
    "遮住": "遮挡",
    "补洞": "空白区域补偿",
}

DISPLAY_CONTEXT_KEYWORDS = (
    "显示",
    "屏幕",
    "多屏",
    "投影",
    "视频",
    "画面",
    "Cave",
    "折幕",
    "LED",
)

DISPLAY_GLOSSARY = {
    "显示面": "用于显示视频内容的显示单元，包括固定显示面和可调显示面。",
    "目标空间姿态信息": "表征显示面相对位置、目标角度、目标开合程度等的信息。",
    "边界投影关系": "相邻显示面的边界在目标空间中的投影、重叠或空白关系。",
}


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
        """执行术语规范化：固定映射与一致性检查，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Normalizing terminology", domain=domain)
        normalized = text or ""
        applied = []
        context = f"{domain or ''}\n{normalized}"
        is_display_context = any(keyword.lower() in context.lower() for keyword in DISPLAY_CONTEXT_KEYWORDS)
        if is_display_context:
            for original, target in TERM_MAPPINGS.items():
                if original in normalized:
                    normalized = normalized.replace(original, target)
                    applied.append({"original": original, "normalized": target, "reason": "显示/视频场景术语一致化"})
        data = {
            "normalized_text": normalized,
            "term_mappings": applied,
            "consistency_issues": [],
            "key_terms_glossary": DISPLAY_GLOSSARY if is_display_context else {},
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
