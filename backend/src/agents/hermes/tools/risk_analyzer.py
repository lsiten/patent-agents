"""
RiskAnalyzerTool - 风险分析工具
识别专利申请过程中的各种风险
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter
from src.core.logging import get_logger

logger = get_logger(__name__)


class RiskAnalyzerTool(HermesTool):
    """
    风险分析工具
    识别专利申请过程中的各种风险
    """
    name = "risk_analyzer"
    description = "分析专利申请过程中的各种风险，提供评估和缓解建议"

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
                    description="技术数据或专利文件内容",
                    required=True,
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
        analysis_type: str,
        tech_data: str,
        prior_art_references: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行风险分析"""
        logger.info("Analyzing risks", type=analysis_type)

        risks = []
        overall_risk_level = "low"

        # 基于分析类型识别风险
        if analysis_type in ["novelty", "overall"]:
            novelty_risks = self._analyze_novelty_risks(tech_data)
            risks.extend(novelty_risks)

        if analysis_type in ["inventive_step", "overall"]:
            inventive_risks = self._analyze_inventive_step_risks(tech_data)
            risks.extend(inventive_risks)

        if analysis_type in ["prior_art", "overall"] and prior_art_references:
            prior_art_risks = self._analyze_prior_art_risks(prior_art_references)
            risks.extend(prior_art_risks)

        if analysis_type in ["support", "overall"]:
            support_risks = self._analyze_support_risks(tech_data)
            risks.extend(support_risks)

        # 计算整体风险等级
        if any(r["severity"] == "critical" for r in risks):
            overall_risk_level = "critical"
        elif any(r["severity"] == "high" for r in risks):
            overall_risk_level = "high"
        elif any(r["severity"] == "medium" for r in risks):
            overall_risk_level = "medium"

        return {
            "analysis_type": analysis_type,
            "overall_risk_level": overall_risk_level,
            "risk_count": len(risks),
            "risks": risks,
            "risk_matrix": self._generate_risk_matrix(risks),
            "mitigation_priorities": self._generate_mitigation_priorities(risks),
            "analysis_timestamp": datetime.now().isoformat(),
        }

    def _analyze_novelty_risks(self, tech_data: str) -> List[Dict]:
        """分析新颖性风险"""
        risks = []
        data_lower = tech_data.lower()

        # 检查是否有过于宽泛的技术描述
        if len(data_lower) < 200:
            risks.append({
                "type": "novelty_insufficient_description",
                "severity": "medium",
                "description": "技术描述不够详细，可能影响新颖性判断的准确性",
                "category": "information",
                "mitigation": "补充更多的技术细节和具体实现方案",
            })

        # 检查是否提到了常见的通用技术
        common_terms = ["人工智能", "机器学习", "深度学习", "神经网络", "区块链", "云计算"]
        if any(term in data_lower for term in common_terms):
            risks.append({
                "type": "novelty_common_tech",
                "severity": "medium",
                "description": "技术方案包含通用技术术语，需要明确具体的创新实现细节",
                "category": "technical",
                "mitigation": "重点描述与通用技术结合的具体创新点和技术效果",
            })

        return risks

    def _analyze_inventive_step_risks(self, tech_data: str) -> List[Dict]:
        """分析创造性风险"""
        risks = []
        data_lower = tech_data.lower()

        # 检查技术效果描述
        if "效果" not in data_lower and "advantage" not in data_lower and "有益" not in data_lower:
            risks.append({
                "type": "inventive_step_no_effects",
                "severity": "high",
                "description": "缺少技术效果的描述，可能影响创造性评估",
                "category": "technical",
                "mitigation": "详细描述技术方案带来的具体技术效果和有益效果",
            })

        return risks

    def _analyze_prior_art_risks(self, prior_art_refs: str) -> List[Dict]:
        """分析现有技术风险"""
        risks = []

        try:
            refs = json.loads(prior_art_refs) if isinstance(prior_art_refs, str) else prior_art_refs
            if isinstance(refs, list) and len(refs) > 5:
                risks.append({
                    "type": "prior_art_high_volume",
                    "severity": "medium",
                    "description": f"发现 {len(refs)} 篇相关现有技术，需要仔细甄别最接近的对比文件",
                    "category": "search",
                    "mitigation": "筛选最相关的3-5篇对比文件进行深度比对分析",
                })
        except (json.JSONDecodeError, TypeError):
            pass

        return risks

    def _analyze_support_risks(self, tech_data: str) -> List[Dict]:
        """分析支持性风险（权利要求是否得到说明书支持）"""
        risks = []
        data_lower = tech_data.lower()

        # 检查实施例数量
        embodiment_count = len(re.findall(r"实施例|embodiment", data_lower))
        if embodiment_count < 2:
            risks.append({
                "type": "support_insufficient_embodiments",
                "severity": "medium",
                "description": "实施例数量可能不足，可能影响权利要求的支持性",
                "category": "drafting",
                "mitigation": "增加多个不同角度的实施例，覆盖权利要求的全部技术特征",
            })

        return risks

    def _generate_risk_matrix(self, risks: List[Dict]) -> Dict[str, int]:
        """生成风险矩阵统计"""
        matrix = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for risk in risks:
            matrix[risk["severity"]] = matrix.get(risk["severity"], 0) + 1
        return matrix

    def _generate_mitigation_priorities(self, risks: List[Dict]) -> List[str]:
        """生成缓解优先级建议"""
        # 按严重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_risks = sorted(risks, key=lambda r: severity_order.get(r["severity"], 99))

        return [
            f"[{risk['severity'].upper()}] {risk['description']} -> {risk['mitigation']}"
            for risk in sorted_risks
        ]
