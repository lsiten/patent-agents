"""
Terminology Normalizer Tool - 术语规范化工具
规范专利文件中的技术术语使用
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)


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
        """执行术语一致性检查：不引入领域默认替换，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Normalizing terminology", domain=domain)
        normalized = text or ""
        term_counts: Dict[str, int] = {}
        for term in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:模块|单元|装置|系统|方法|步骤|区域|参数|模型|图像|数据|信号|组件|机构|部件)", normalized):
            term_counts[term] = term_counts.get(term, 0) + 1
        repeated_terms = [
            {"term": term, "count": count}
            for term, count in sorted(term_counts.items(), key=lambda item: (-item[1], item[0]))
            if count > 1
        ][:20]
        data = {
            "normalized_text": normalized,
            "term_mappings": [],
            "consistency_issues": [],
            "key_terms_glossary": {},
            "repeated_terms": repeated_terms,
            "note": "本工具只返回当前文本中的术语一致性信号，不做领域默认替换；正式术语取舍由专利撰写 Agent 判断。",
        }
        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
