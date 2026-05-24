"""
Hermes 工具注册模块
每个工具模块提供自己的 register() 函数，由本模块聚合调用
"""

from .task_planner import TaskPlannerTool, register as register_task_planner
from .quality_assessor import QualityAssessorTool, register as register_quality_assessor
from .report_generator import ReportGeneratorTool, register as register_report_generator
from .risk_analyzer import RiskAnalyzerTool, register as register_risk_analyzer

__all__ = [
    "TaskPlannerTool",
    "QualityAssessorTool",
    "ReportGeneratorTool",
    "RiskAnalyzerTool",
    "register_all_tools",
]


def register_all_tools(factory) -> None:
    """注册所有 Hermes 工具到 factory"""
    register_task_planner(factory)
    register_quality_assessor(factory)
    register_report_generator(factory)
    register_risk_analyzer(factory)
