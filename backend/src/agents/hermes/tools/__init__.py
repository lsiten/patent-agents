"""
Hermes 工具注册模块
每个工具模块提供自己的 register() 函数，由本模块聚合调用
"""

from .task_planner import TaskPlannerTool, register as register_task_planner
from .quality_assessor import QualityAssessorTool, register as register_quality_assessor
from .report_generator import ReportGeneratorTool, register as register_report_generator
from .risk_analyzer import RiskAnalyzerTool, register as register_risk_analyzer
from .ipc_classifier import IPCClassifierTool, register as register_ipc_classifier
from .tech_feature_extractor import TechFeatureExtractorTool, register as register_tech_feature_extractor
from .scenario_miner import ScenarioMinerTool, register as register_scenario_miner
from .patent_search import PatentSearchTool, register as register_patent_search
from .similarity_analyzer import SimilarityAnalyzerTool, register as register_similarity_analyzer
from .patentability_scorer import PatentabilityScorerTool, register as register_patentability_scorer
from .claim_drafter import ClaimDrafterTool, register as register_claim_drafter
from .description_writer import DescriptionWriterTool, register as register_description_writer
from .terminology_normalizer import TerminologyNormalizerTool, register as register_terminology_normalizer
from .support_checker import SupportCheckerTool, register as register_support_checker
from .compliance_checker import ComplianceCheckerTool, register as register_compliance_checker
from .claim_quality_analyzer import ClaimQualityAnalyzerTool, register as register_claim_quality_analyzer
from .support_verifier import SupportVerifierTool, register as register_support_verifier
from .oa_predictor import OAPredictorTool, register as register_oa_predictor
from .creative_thinking import CreativeThinkingTool, register as register_creative_thinking
from .patent_strategy_guide import PatentStrategyGuideTool, register as register_patent_strategy_guide
from .agent_selector import AgentSelectorTool, register as register_agent_selector

__all__ = [
    "TaskPlannerTool",
    "QualityAssessorTool",
    "ReportGeneratorTool",
    "RiskAnalyzerTool",
    "IPCClassifierTool",
    "TechFeatureExtractorTool",
    "ScenarioMinerTool",
    "PatentSearchTool",
    "SimilarityAnalyzerTool",
    "PatentabilityScorerTool",
    "ClaimDrafterTool",
    "DescriptionWriterTool",
    "TerminologyNormalizerTool",
    "SupportCheckerTool",
    "ComplianceCheckerTool",
    "ClaimQualityAnalyzerTool",
    "SupportVerifierTool",
    "OAPredictorTool",
    "CreativeThinkingTool",
    "PatentStrategyGuideTool",
    "AgentSelectorTool",
    "register_all_tools",
]


def register_all_tools(factory) -> None:
    """注册所有 Hermes 工具到 factory"""
    register_task_planner(factory)
    register_quality_assessor(factory)
    register_report_generator(factory)
    register_risk_analyzer(factory)
    register_ipc_classifier(factory)
    register_tech_feature_extractor(factory)
    register_scenario_miner(factory)
    register_patent_search(factory)
    register_similarity_analyzer(factory)
    register_patentability_scorer(factory)
    register_claim_drafter(factory)
    register_description_writer(factory)
    register_terminology_normalizer(factory)
    register_support_checker(factory)
    register_compliance_checker(factory)
    register_claim_quality_analyzer(factory)
    register_support_verifier(factory)
    register_oa_predictor(factory)
    register_creative_thinking(factory)
    register_patent_strategy_guide(factory)
    register_agent_selector(factory)
