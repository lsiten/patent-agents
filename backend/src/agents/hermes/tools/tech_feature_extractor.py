"""
Tech Feature Extractor Tool - 技术特征提取工具
从技术描述中提取关键技术特征和创新点
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

FEATURE_RULES = [
    {
        "name": "目标空间姿态信息获取",
        "keywords": ["姿态", "角度", "位置", "开合", "身高", "用户"],
        "description": "获取显示面、用户或内容相关的姿态/位置/角度参数，作为生成显示空间目标姿态的输入。",
        "technical_significance": "为动态显示面调整和个性化显示提供参数基础。",
    },
    {
        "name": "目标空间姿态生成",
        "keywords": ["目标", "生成", "调节", "可调", "屏幕", "显示装置"],
        "description": "根据输入参数生成一个或多个可调显示装置的目标姿态或目标显示面布局。",
        "technical_significance": "将用户需求、显示范围和内容约束转化为可执行的显示控制目标。",
    },
    {
        "name": "边界投影与重叠/空白区域判定",
        "keywords": ["边界", "投影", "重叠", "空白", "遮挡", "缝隙"],
        "description": "确定相邻显示面之间的边界投影关系，并识别外转产生的空白区域或内转产生的遮挡/重叠区域。",
        "technical_significance": "为后续裁剪、补偿、删除和重映射提供空间判定依据。",
    },
    {
        "name": "视频内容补偿、裁剪与重映射",
        "keywords": ["补偿", "裁剪", "删除", "重映射", "过渡", "连续"],
        "description": "针对姿态变化后的显示区域生成补充显示数据，或对重叠/遮挡内容进行裁剪、删除、重映射及过渡处理。",
        "technical_significance": "保持多显示面视频内容连续性，降低折幕姿态变化造成的割裂感。",
    },
    {
        "name": "多显示面同步输出控制",
        "keywords": ["同步", "输出", "多屏", "显示面", "Cave", "折幕"],
        "description": "将处理后的视频内容同步输出至对应显示面，维持沉浸式空间中的一致显示效果。",
        "technical_significance": "保证多显示面协同显示和沉浸式观看体验。",
    },
]


def _normalize_text(text: str) -> str:
    text = re.sub(r"[\u4e00-\u9fa5A-Za-z]+?\(\d{2}:\d{2}:\d{2}\)[:：]", " ", text or "")
    text = re.sub(r"\(\d{2}:\d{2}:\d{2}\)[:：]?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


class TechFeatureExtractorTool(HermesTool):
    """技术特征提取工具"""
    name = "tech_feature_extractor"
    description = "从技术描述中提取关键技术特征、创新点和解决的技术问题"

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
        """执行技术特征提取。

        工具本身不调用 LLM；Hermes Agent 调用本工具后，基于工具返回
        继续综合、补全和输出需求分析 JSON。
        """
        start_time = datetime.now()
        logger.info("Extracting technical features from description")

        text = _normalize_text(tech_description)
        features = []
        for rule in FEATURE_RULES:
            if _contains_any(text, rule["keywords"]):
                features.append(
                    {
                        "name": rule["name"],
                        "description": rule["description"],
                        "is_innovative": True,
                        "technical_significance": rule["technical_significance"],
                        "evidence_keywords": [
                            keyword for keyword in rule["keywords"] if keyword.lower() in text.lower()
                        ],
                    }
                )

        if not features:
            features.append(
                {
                    "name": "结构化技术处理流程",
                    "description": "从输入信息中形成可执行的数据处理或控制流程。",
                    "is_innovative": True,
                    "technical_significance": "为专利方案抽象为方法、系统和介质权利要求提供基础。",
                    "evidence_keywords": [],
                }
            )

        problem_parts = []
        if _contains_any(text, ["空白", "缝隙", "补偿"]):
            problem_parts.append("显示面姿态变化后产生空白或缝隙")
        if _contains_any(text, ["遮挡", "重叠", "裁剪", "删除"]):
            problem_parts.append("显示内容因内转或边界变化产生遮挡、重叠或错位")
        if _contains_any(text, ["连续", "沉浸", "同步"]):
            problem_parts.append("多显示面内容连续性和沉浸感不足")
        technical_problem = "；".join(problem_parts) or "非结构化技术构思需要转化为可执行、可保护的技术方案"

        core_innovation = "、".join(feature["name"] for feature in features[:4])
        beneficial_effects = [
            "提升折幕/Cave空间中多显示面画面的连续性",
            "降低姿态变化导致的空白、遮挡、重叠和内容错位",
            "支持可调显示装置在不同用户或内容条件下的自适应显示",
        ]

        data = {
            "features": features,
            "core_innovation": core_innovation,
            "technical_problem": technical_problem,
            "beneficial_effects": beneficial_effects,
            "cleaned_description_preview": text[:800],
        }

        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
