"""
Similarity Analyzer Tool - 相似度分析工具
分析发明与现有技术之间的相似度和差异
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Set

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from src.core.logging import get_logger

logger = get_logger(__name__)

def _tokens(text: str) -> Set[str]:
    words = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", text or "")
    return {word.lower() for word in words if len(word.strip()) >= 2}


def _candidate_terms(text: str, limit: int = 12) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fa5]{2,}", text or "")
    ordered: List[str] = []
    for token in tokens:
        clean = token.strip().lower()
        if len(clean) < 2 or clean in ordered:
            continue
        ordered.append(clean)
        if len(ordered) >= limit:
            break
    return ordered


class SimilarityAnalyzerTool(HermesTool):
    """相似度客观信号工具"""
    name = "similarity_analyzer"
    description = "计算发明方案与现有技术的术语/特征重合信号；风险与创造性结论由 Agent 判断"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "invention": HermesToolParameter(
                    type="string",
                    description="待分析的发明技术方案描述",
                    required=True,
                ),
                "prior_art": HermesToolParameter(
                    type="string",
                    description="对比的现有技术描述（可含多篇）",
                    required=True,
                ),
            },
        )

    async def execute(
        self, invention: str, prior_art: str, **kwargs
    ) -> Dict[str, Any]:
        """执行相似度分析：工具只做确定性文本/特征重合计算，不调用 LLM。"""
        start_time = datetime.now()
        logger.info("Analyzing similarity between invention and prior art")

        try:
            invention_tokens = _tokens(invention)
            prior_tokens = _tokens(prior_art)
            overlap = invention_tokens & prior_tokens
            token_similarity = len(overlap) / max(len(invention_tokens), 1)
            candidate_features = _candidate_terms(invention)
            feature_comparison: List[Dict[str, Any]] = []
            common_features = 0
            for feature in candidate_features:
                in_invention = feature in invention_tokens
                in_prior = feature in prior_tokens
                common_features += int(in_invention and in_prior)
                feature_comparison.append(
                    {
                        "feature": feature,
                        "in_invention": in_invention,
                        "in_prior_art": in_prior,
                        "difference": "现有技术已涉及" if in_invention and in_prior else ("本方案区别特征" if in_invention else "未体现"),
                    }
                )
            feature_similarity = common_features / max(len(candidate_features), 1)
            overall = round(min(0.95, max(0.05, token_similarity * 0.35 + feature_similarity * 0.65)), 2)
            key_differences = [
                item["feature"] for item in feature_comparison
                if item["in_invention"] and not item["in_prior_art"]
            ]
            data = {
                "text_feature_overlap": overall,
                "feature_comparison": feature_comparison,
                "key_differences": key_differences,
                "overlap_terms": sorted(overlap)[:30],
                "requires_agent_judgment": [
                    "该重合度是否构成新颖性/创造性风险",
                    "key_differences 是否足以支撑区别技术效果",
                ],
            }

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                raw_response=json.dumps(data, ensure_ascii=False),
                start_time=start_time,
            )

        except Exception as e:
            logger.error(f"Similarity analysis failed: {e}")
            return make_tool_output(
                tool_name=self.name,
                data={},
                success=False,
                error=str(e),
                start_time=start_time,
            )
