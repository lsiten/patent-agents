"""
RiskAnalyzerTool - 确定性风险信号工具

该工具只返回可代码化触发的风险信号，不在工具层判断风险等级或最终处理策略。
风险严重程度、是否阻断流程以及修复优先级必须由调用该工具的 Hermes Agent LLM 决定。
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


class RiskAnalyzerTool(HermesTool):
    """提取专利申请过程中的确定性风险信号。"""

    name = "risk_analyzer"
    description = "提取新颖性、创造性、现有技术和支持性相关的客观风险信号；风险判断由Agent完成"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "analysis_type": HermesToolParameter(
                    type="string",
                    description="分析类型：novelty / inventive_step / prior_art / support / overall",
                    required=True,
                ),
                "tech_data": HermesToolParameter(
                    type="string",
                    description="技术数据或专利文件内容（也可用 patent_document 或 document 参数名传入）",
                    required=True,
                ),
                "patent_document": HermesToolParameter(
                    type="string",
                    description="专利文件内容（与 tech_data 同义，二选一即可）",
                    required=False,
                ),
                "document": HermesToolParameter(
                    type="string",
                    description="文档内容（与 tech_data 同义，二选一即可）",
                    required=False,
                ),
                "prior_art_references": HermesToolParameter(
                    type="string",
                    description="现有技术参考文件列表（JSON格式）",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        analysis_type: Optional[str] = None,
        tech_data: Optional[str] = None,
        patent_document: Optional[str] = None,
        document: Optional[str] = None,
        prior_art_references: Optional[str] = None,
        risk_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提取风险信号。"""
        resolved_type = analysis_type or risk_type or "overall"
        resolved_tech_data = tech_data or patent_document or document or ""
        if not resolved_tech_data:
            return {
                "analysis_type": resolved_type,
                "signal_count": 0,
                "objective_risk_signals": [],
                "requires_agent_judgment": ["缺少输入时是否暂停流程或要求补充信息"],
                "analysis_timestamp": datetime.now().isoformat(),
                "error": "缺少技术数据或专利文件内容",
            }

        logger.info("Collecting objective risk signals", type=resolved_type)

        signals: List[Dict[str, Any]] = []
        if resolved_type in {"novelty", "overall"}:
            signals.extend(self._collect_novelty_signals(resolved_tech_data))
        if resolved_type in {"inventive_step", "overall"}:
            signals.extend(self._collect_inventive_step_signals(resolved_tech_data))
        if resolved_type in {"prior_art", "overall"} and prior_art_references:
            signals.extend(self._collect_prior_art_signals(prior_art_references))
        if resolved_type in {"support", "overall"}:
            signals.extend(self._collect_support_signals(resolved_tech_data))

        return {
            "analysis_type": resolved_type,
            "signal_count": len(signals),
            "objective_risk_signals": signals,
            "requires_agent_judgment": [
                "信号是否构成实质风险",
                "风险严重程度",
                "是否阻断当前流程",
                "是否调度对应Agent修复以及修复优先级",
            ],
            "analysis_timestamp": datetime.now().isoformat(),
        }

    def _collect_novelty_signals(self, tech_data: str) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        data_lower = tech_data.lower()

        if len(data_lower) < 200:
            signals.append({
                "type": "short_technical_description",
                "category": "information",
                "signal": "技术描述长度小于200字符",
                "candidate_action": "补充更多技术细节和具体实现方案",
                "rule_triggered": True,
            })

        common_terms = ["人工智能", "机器学习", "深度学习", "神经网络", "区块链", "云计算"]
        matched_common_terms = [term for term in common_terms if term in data_lower]
        if matched_common_terms:
            signals.append({
                "type": "common_technology_terms_present",
                "category": "technical",
                "signal": "出现通用技术术语",
                "matched_terms": matched_common_terms,
                "candidate_action": "要求Agent明确与通用技术结合的具体创新实现和技术效果",
                "rule_triggered": True,
            })

        return signals

    def _collect_inventive_step_signals(self, tech_data: str) -> List[Dict[str, Any]]:
        data_lower = tech_data.lower()
        if "效果" in data_lower or "advantage" in data_lower or "有益" in data_lower:
            return []
        return [{
            "type": "technical_effect_terms_absent",
            "category": "technical",
            "signal": "未发现技术效果相关关键词",
            "candidate_action": "要求Agent补充具体技术效果和有益效果",
            "rule_triggered": True,
        }]

    def _collect_prior_art_signals(self, prior_art_refs: str) -> List[Dict[str, Any]]:
        try:
            refs = json.loads(prior_art_refs) if isinstance(prior_art_refs, str) else prior_art_refs
        except (json.JSONDecodeError, TypeError):
            return [{
                "type": "prior_art_reference_parse_failed",
                "category": "search",
                "signal": "现有技术参考无法解析为JSON",
                "candidate_action": "要求Agent确认检索输出格式",
                "rule_triggered": True,
            }]

        if isinstance(refs, list) and len(refs) > 5:
            return [{
                "type": "many_prior_art_references",
                "category": "search",
                "signal": f"现有技术参考数量为 {len(refs)}",
                "candidate_action": "要求Agent筛选最相关对比文件并做差异分析",
                "rule_triggered": True,
            }]
        return []

    def _collect_support_signals(self, tech_data: str) -> List[Dict[str, Any]]:
        data_lower = tech_data.lower()
        embodiment_count = len(re.findall(r"实施例|embodiment", data_lower))
        if embodiment_count >= 2:
            return []
        return [{
            "type": "low_embodiment_marker_count",
            "category": "drafting",
            "signal": f"实施例关键词出现次数为 {embodiment_count}",
            "candidate_action": "要求Agent检查是否需要补充不同角度的实施例",
            "rule_triggered": True,
        }]
