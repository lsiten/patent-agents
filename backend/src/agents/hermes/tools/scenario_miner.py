"""
Scenario Miner Tool - 应用场景挖掘工具
发现技术发明的潜在应用场景和扩展领域
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

DOMAIN_RULES = [
    (["算法", "模型", "训练", "识别", "预测", "数据"], "数据处理/人工智能"),
    (["控制", "传感", "执行", "驱动", "设备", "装置"], "自动化控制/设备系统"),
    (["通信", "网络", "终端", "服务器", "同步", "传输"], "通信与网络系统"),
    (["材料", "结构", "组件", "连接", "安装", "机械"], "机械结构/材料工程"),
    (["显示", "视频", "图像", "屏幕", "投影", "LED"], "显示与图像处理"),
]


def _parse_features(features: str) -> list[str]:
    try:
        parsed = json.loads(features or "[]")
    except json.JSONDecodeError:
        parsed = features or ""
    if isinstance(parsed, list):
        return [
            str(item.get("name") or item.get("feature_name") or item)
            for item in parsed
            if item
        ]
    if isinstance(parsed, dict):
        raw = parsed.get("features") or parsed.get("key_innovative_features") or []
        return [str(item.get("name") or item.get("feature_name") or item) for item in raw]
    return [str(parsed)] if parsed else []


def _normalize_text(text: str) -> str:
    text = re.sub(r"[\u4e00-\u9fa5A-Za-z]+?\(\d{2}:\d{2}:\d{2}\)[:：]", " ", text or "")
    text = re.sub(r"\(\d{2}:\d{2}:\d{2}\)[:：]?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _matches(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _domain_from_text(text: str) -> str:
    for keywords, domain in DOMAIN_RULES:
        if _matches(text, keywords):
            return domain
    return ""


class ScenarioMinerTool(HermesTool):
    """应用场景挖掘工具"""
    name = "scenario_miner"
    description = "根据技术描述和特征挖掘潜在应用场景、目标用户和市场价值"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "tech_description": HermesToolParameter(
                    type="string",
                    description="技术发明描述",
                    required=True,
                ),
                "features": HermesToolParameter(
                    type="string",
                    description="关键技术特征列表（JSON或文本）",
                    required=False,
                ),
            },
        )

    async def execute(
        self, tech_description: str, features: str = "", **kwargs
    ) -> Dict[str, Any]:
        """执行应用场景挖掘。

        工具不调用 LLM；它基于技术文本和上游特征做本地场景匹配，
        再由 Hermes Agent 综合生成最终需求分析。
        """
        start_time = datetime.now()
        logger.info("Mining application scenarios")

        text = _normalize_text(tech_description + " " + " ".join(_parse_features(features)))
        domain = _domain_from_text(text)
        matched_keywords = [
            keyword
            for keywords, _domain in DOMAIN_RULES
            if _domain == domain
            for keyword in keywords
            if keyword.lower() in text.lower()
        ]
        scenarios = []
        if domain and matched_keywords:
            scenarios.append(
                {
                    "candidate_domain": domain,
                    "description": "本地规则仅识别到候选领域关键词；具体应用场景、目标用户和市场价值必须由 Agent 结合发明事实判断。",
                    "confidence": 0.62,
                    "evidence_keywords": matched_keywords,
                }
            )

        data = {
            "scenario_signals": scenarios,
            "extension_directions": [],
            "market_assessment": "工具仅返回关键词证据，不生成通用场景结论；最终应用场景和保护布局由 Agent 判断。",
            "requires_agent_judgment": True,
        }

        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
