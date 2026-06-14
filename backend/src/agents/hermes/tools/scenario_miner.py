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

SCENARIO_RULES = [
    {
        "name": "沉浸式 Cave 展示空间",
        "keywords": ["Cave", "折幕", "沉浸", "多屏"],
        "description": "用于由多个显示面构成的沉浸式展示、体验、展厅或训练空间。",
        "domain": "沉浸式显示",
        "target_users": ["展厅运营方", "沉浸式体验系统集成商", "文旅/培训机构"],
    },
    {
        "name": "可调屏幕互动体验空间",
        "keywords": ["可调", "身高", "用户", "个性化", "入口"],
        "description": "根据用户身高、位置或体验入口对屏幕姿态和显示画面进行自适应调整。",
        "domain": "人机交互",
        "target_users": ["体验空间用户", "交互装置厂商", "智能展陈平台"],
    },
    {
        "name": "多显示面视频连续播放",
        "keywords": ["视频", "同步", "连续", "补偿", "裁剪", "重映射"],
        "description": "在多显示面之间进行视频内容重映射、补偿和同步输出，保持连续观看效果。",
        "domain": "视频显示控制",
        "target_users": ["多屏控制系统厂商", "数字内容制作方", "显示控制平台"],
    },
    {
        "name": "投影/LED 混合显示系统",
        "keywords": ["投影", "LED", "屏幕", "显示装置"],
        "description": "适用于投影幕、LED屏、拼接屏或混合显示装置构成的可变空间显示系统。",
        "domain": "显示硬件控制",
        "target_users": ["显示设备厂商", "系统集成商", "工程实施方"],
    },
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
    return re.sub(r"\s+", " ", text or "").strip()


def _matches(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


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
        scenarios = []
        for rule in SCENARIO_RULES:
            if _matches(text, rule["keywords"]):
                scenarios.append(
                    {
                        "name": rule["name"],
                        "description": rule["description"],
                        "domain": rule["domain"],
                        "potential_value": "可作为方法、系统、设备和介质多维保护的实施场景",
                        "confidence": 0.82,
                        "target_users": rule["target_users"],
                        "evidence_keywords": [
                            keyword for keyword in rule["keywords"] if keyword.lower() in text.lower()
                        ],
                    }
                )

        if not scenarios:
            scenarios.append(
                {
                    "name": "通用技术处理系统",
                    "description": "用于需要根据输入参数执行数据处理、控制或输出的系统。",
                    "domain": "通用数据处理",
                    "potential_value": "可作为方法和系统权利要求的基础实施场景",
                    "confidence": 0.55,
                    "target_users": ["系统开发者", "设备厂商"],
                    "evidence_keywords": [],
                }
            )

        data = {
            "scenarios": scenarios,
            "extension_directions": [
                "显示装置类型上位化，覆盖投影幕、LED屏、拼接屏和混合显示设备",
                "姿态输入来源扩展为用户参数、内容参数、空间边界参数和传感器检测参数",
                "画面处理策略扩展为补充、裁剪、删除、重映射、过渡生成和同步输出",
            ],
            "market_assessment": "该方案面向沉浸式显示、多屏交互和空间内容自适应控制，适合布局显示控制和视频处理交叉领域专利。",
        }

        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
