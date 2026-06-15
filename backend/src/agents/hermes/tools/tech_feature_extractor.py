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

ACTION_KEYWORDS = {
    "input": ["获取", "采集", "接收", "输入", "检测", "识别", "读取"],
    "process": ["确定", "生成", "计算", "处理", "控制", "匹配", "训练", "分析"],
    "output": ["输出", "显示", "发送", "存储", "反馈", "执行", "更新"],
    "exception": ["异常", "失败", "冲突", "风险", "误差", "补偿", "校正"],
}


def _normalize_text(text: str) -> str:
    text = re.sub(r"[\u4e00-\u9fa5A-Za-z]+?\(\d{2}:\d{2}:\d{2}\)[:：]", " ", text or "")
    text = re.sub(r"\(\d{2}:\d{2}:\d{2}\)[:：]?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _ordered_terms(text: str, limit: int = 12) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", text or "")
    stop_words = {
        "这个",
        "然后",
        "就是",
        "可以",
        "需要",
        "进行",
        "一个",
        "一种",
        "我们",
        "他们",
        "东西",
        "开头",
        "比如",
        "可能",
        "相当于",
    }
    ordered = []
    for term in terms:
        clean = term.strip()
        if len(clean) < 2 or clean in stop_words or clean in ordered:
            continue
        ordered.append(clean)
        if len(ordered) >= limit:
            break
    return ordered


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
        key_terms = _ordered_terms(text)
        for category, keywords in ACTION_KEYWORDS.items():
            evidence = [keyword for keyword in keywords if keyword.lower() in text.lower()]
            if evidence:
                label = {
                    "input": "输入信息获取",
                    "process": "核心处理逻辑",
                    "output": "结果输出或执行",
                    "exception": "异常处理或校正机制",
                }[category]
                features.append(
                    {
                        "name": label,
                        "description": "检测到该类技术动作信号；具体技术特征名称和保护重点必须由 Agent 结合完整发明事实判断。",
                        "is_innovative": True,
                        "technical_significance": "为 Agent 识别方法步骤、系统模块和从属限定提供客观关键词证据。",
                        "evidence_keywords": evidence,
                    }
                )

        if not features:
            features.append(
                {
                    "name": "结构化技术处理流程",
                    "description": "未检测到足够稳定的动作关键词；需要 Agent 通过 LLM 结合全文判断真实技术流程。",
                    "is_innovative": True,
                    "technical_significance": "提示 Agent 不应依赖本地工具直接得出创新特征。",
                    "evidence_keywords": [],
                }
            )

        problem_parts = []
        if _contains_any(text, ["问题", "缺陷", "不足", "难以", "无法"]):
            problem_parts.append("原始描述中包含待解决问题信号")
        if _contains_any(text, ["误差", "冲突", "异常", "失败", "风险"]):
            problem_parts.append("原始描述中包含异常或可靠性问题信号")
        if _contains_any(text, ["效率", "准确", "稳定", "同步", "连续", "安全"]):
            problem_parts.append("原始描述中包含性能或效果改进信号")
        technical_problem = "；".join(problem_parts) or "非结构化技术构思需要转化为可执行、可保护的技术方案"

        core_innovation = "、".join(feature["name"] for feature in features[:4])
        beneficial_effects = [
            "提高当前技术流程的可执行性和稳定性",
            "降低当前技术问题导致的异常、误差或处理失败风险",
            "为方法、系统、设备和介质权利要求提供可对应的技术效果",
        ]

        data = {
            "features": features,
            "core_innovation": core_innovation,
            "technical_problem": technical_problem,
            "beneficial_effects": beneficial_effects,
            "evidence_terms": key_terms,
            "requires_agent_judgment": True,
        }

        return make_tool_output(
            tool_name=self.name,
            data=data,
            success=True,
            raw_response=json.dumps(data, ensure_ascii=False),
            start_time=start_time,
        )
