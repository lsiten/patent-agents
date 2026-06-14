"""
IPC Classifier Tool - IPC 分类工具
帮助需求分析 Agent 对技术方案进行 IPC 国际专利分类
"""
import json
import re
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

IPC_RULES = [
    {
        "code": "G06T 7/00",
        "keywords": ["图像", "视频", "画面", "视觉", "投影", "重映射", "裁剪", "补偿"],
        "reason": "涉及视频/图像画面分析、映射、裁剪或补偿处理。",
    },
    {
        "code": "G09G 5/00",
        "keywords": ["显示", "屏幕", "显示面", "多屏", "拼接屏", "LED", "折幕", "Cave"],
        "reason": "涉及显示装置控制、多显示面输出或显示参数调节。",
    },
    {
        "code": "H04N 5/262",
        "keywords": ["视频输出", "视频内容", "同步输出", "画面连续", "多屏同步"],
        "reason": "涉及视频信号处理、组合或同步输出。",
    },
    {
        "code": "G06F 3/01",
        "keywords": ["交互", "用户", "身高", "姿态", "个性化", "入口"],
        "reason": "涉及用户交互、姿态/个性化输入与控制。",
    },
    {
        "code": "G06F 16/00",
        "keywords": ["映射关系", "参数", "坐标", "边界", "模型"],
        "reason": "涉及数据结构、参数关系或映射关系处理。",
    },
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _score_rule(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lower)


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
        """执行 IPC 分类。

        这是 Hermes 工具的本地确定性能力，不在工具内部再次调用 LLM。
        Agent 负责推理与综合；工具只根据技术文本做可追溯分类匹配。
        """
        start_time = datetime.now()
        logger.info("Classifying technology into IPC categories")

        text = _normalize_text(tech_description)
        matches = []
        for rule in IPC_RULES:
            score = _score_rule(text, rule["keywords"])
            if score:
                matches.append({**rule, "score": score})
        matches.sort(key=lambda item: item["score"], reverse=True)

        if not matches:
            matches = [
                {
                    "code": "G06F 17/00",
                    "score": 1,
                    "reason": "文本描述涉及数据处理流程，但未命中特定领域关键词。",
                }
            ]

        primary = matches[0]
        secondary = [item["code"] for item in matches[1:4]]
        rationale_parts = [f"{item['code']}: {item['reason']}" for item in matches[:4]]
        confidence = min(0.95, 0.55 + primary["score"] * 0.08 + len(secondary) * 0.04)

        data = {
            "primary_code": primary["code"],
            "secondary_codes": secondary,
            "classification_rationale": "；".join(rationale_parts),
            "confidence": round(confidence, 2),
            "matched_keywords": {
                item["code"]: [
                    keyword
                    for keyword in next(rule for rule in IPC_RULES if rule["code"] == item["code"]).get("keywords", [])
                    if keyword.lower() in text.lower()
                ]
                for item in matches
                if any(rule["code"] == item["code"] for rule in IPC_RULES)
            },
        }

        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
