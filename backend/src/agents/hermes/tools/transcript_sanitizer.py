# -*- coding: utf-8 -*-
"""Transcript sanitizer tool for patent disclosures."""
import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger
from src.core.patent.compliance import sanitize_transcript_text

logger = get_logger(__name__)


class TranscriptSanitizerTool(HermesTool):
    """Remove transcript artifacts before agents derive patent facts."""

    name = "transcript_sanitizer"
    description = "清洗交底逐字稿中的时间戳、说话人、会议格式和口语噪声，保留技术事实"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "text": HermesToolParameter(
                    type="string",
                    description="原始技术交底文本或逐字稿内容",
                    required=True,
                ),
            },
        )

    async def execute(self, text: str, **kwargs: Any) -> Dict[str, Any]:
        start_time = datetime.now()
        try:
            result = sanitize_transcript_text(text or "")
            data = {
                **result,
                "objective_signal": "工具只做格式清洗，不判断专利主题、创新点或内容质量。",
            }
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )
        except Exception as exc:
            logger.error(f"Transcript sanitizer failed: {exc}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(exc),
                start_time=start_time,
            )
