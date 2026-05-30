"""
Patent Tools Adapter — 将现有 21 个 HermesTool 类桥接为 hermes-agent registry 格式

该模块在 hermes-agent 框架中注册专利领域的自定义工具集 (toolset="patent")，
使得 AIAgent 实例化时通过 enabled_toolsets=["patent"] 即可启用所有专利工具。
"""
import asyncio
import json
import logging
import os
import tempfile
import time
from typing import Any, Dict

from tools.registry import registry

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=120)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _json_result(result: Any) -> str:
    """将工具结果序列化为 JSON 字符串"""
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def _save_result_to_temp_file(tool_name: str, result_str: str) -> str:
    """
    将工具结果写入临时文件，确保内容不因 LLM max_tokens 截断而丢失。

    Args:
        tool_name: 工具名称，用于文件名
        result_str: 工具结果字符串

    Returns:
        写入的文件路径
    """
    # 使用 HERMES_HOME/tool_outputs/ 目录（如不可用则回退到系统临时目录）
    hermes_home = os.environ.get("HERMES_HOME", "")
    if hermes_home:
        out_dir = os.path.join(hermes_home, "tool_outputs")
    else:
        out_dir = os.path.join(tempfile.gettempdir(), "patent_tool_outputs")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = int(time.time() * 1000)
    safe_name = tool_name.replace("/", "_").replace(" ", "_")
    filepath = os.path.join(out_dir, f"{safe_name}_{timestamp}.json")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result_str)
        logger.debug("Tool result saved to temp file: %s (%d bytes)", filepath, len(result_str))
    except Exception as e:
        logger.warning("Failed to save tool result to temp file: %s", e)

    return filepath


def _make_temp_file_saver(tool_name: str):
    """
    创建一个包装器，在调用工具 handler 后将结果写入临时文件。
    在原始结果末尾追加文件路径引用，方便 LLM 和下游访问。

    Args:
        tool_name: 工具名称，用于文件名
    """
    def decorator(handler):
        def wrapped(args: Dict[str, Any], **kw) -> str:
            result_str = handler(args, **kw)
            filepath = _save_result_to_temp_file(tool_name, result_str)
            # 追加文件引用（不影响原始结果的结构化解析）
            return result_str + f"\n\n[TOOL_OUTPUT_SAVED_TO]: {filepath}"
        return wrapped
    return decorator


# ============ Tool Handlers ============

def _handle_ipc_classifier(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.ipc_classifier import IPCClassifierTool
    tool = IPCClassifierTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_tech_feature_extractor(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.tech_feature_extractor import TechFeatureExtractorTool
    tool = TechFeatureExtractorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_scenario_miner(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.scenario_miner import ScenarioMinerTool
    tool = ScenarioMinerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_patent_search(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.patent_search import PatentSearchTool
    tool = PatentSearchTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_similarity_analyzer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.similarity_analyzer import SimilarityAnalyzerTool
    tool = SimilarityAnalyzerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_patentability_scorer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.patentability_scorer import PatentabilityScorerTool
    tool = PatentabilityScorerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_claim_drafter(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.claim_drafter import ClaimDrafterTool
    tool = ClaimDrafterTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_description_writer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.description_writer import DescriptionWriterTool
    tool = DescriptionWriterTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_terminology_normalizer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.terminology_normalizer import TerminologyNormalizerTool
    tool = TerminologyNormalizerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_support_checker(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.support_checker import SupportCheckerTool
    tool = SupportCheckerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_compliance_checker(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.compliance_checker import ComplianceCheckerTool
    tool = ComplianceCheckerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_claim_quality_analyzer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.claim_quality_analyzer import ClaimQualityAnalyzerTool
    tool = ClaimQualityAnalyzerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_support_verifier(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.support_verifier import SupportVerifierTool
    tool = SupportVerifierTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_oa_predictor(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.oa_predictor import OAPredictorTool
    tool = OAPredictorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_creative_thinking(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.creative_thinking import CreativeThinkingTool
    tool = CreativeThinkingTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_patent_strategy_guide(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.patent_strategy_guide import PatentStrategyGuideTool
    tool = PatentStrategyGuideTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_agent_selector(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.agent_selector import AgentSelectorTool
    tool = AgentSelectorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_task_planner(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.task_planner import TaskPlannerTool
    tool = TaskPlannerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_quality_assessor(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.quality_assessor import QualityAssessorTool
    tool = QualityAssessorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_report_generator(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.report_generator import ReportGeneratorTool
    tool = ReportGeneratorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_risk_analyzer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.risk_analyzer import RiskAnalyzerTool
    tool = RiskAnalyzerTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_dispatch_specialist(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.dispatch_specialist import DispatchSpecialistTool
    tool = DispatchSpecialistTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_patent_docx_generator(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.patent_docx_generator import PatentDocxGeneratorTool
    tool = PatentDocxGeneratorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_prior_art_comparator(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.prior_art_comparator import PriorArtComparatorTool
    tool = PriorArtComparatorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


# ============ Tool Schemas ============

PATENT_TOOL_DEFINITIONS = [
    {
        "name": "ipc_classifier",
        "schema": {
            "name": "ipc_classifier",
            "description": "根据技术描述进行 IPC 国际专利分类，返回主分类号和次要分类号",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术发明描述文本"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_ipc_classifier,
        "emoji": "🏷️",
    },
    {
        "name": "tech_feature_extractor",
        "schema": {
            "name": "tech_feature_extractor",
            "description": "从技术描述中提取关键技术特征、创新点和解决的技术问题",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术发明描述文本"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_tech_feature_extractor,
        "emoji": "🔍",
    },
    {
        "name": "scenario_miner",
        "schema": {
            "name": "scenario_miner",
            "description": "根据技术描述和特征挖掘潜在应用场景、目标用户和市场价值",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术发明描述"},
                    "features": {"type": "string", "description": "关键技术特征列表"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_scenario_miner,
        "emoji": "💡",
    },
    {
        "name": "patent_search",
        "schema": {
            "name": "patent_search",
            "description": "在多源专利数据库(USPTO/EPO/CNIPA)中检索相关现有技术",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询关键词或技术描述"},
                    "sources": {"type": "string", "description": "数据源(逗号分隔): uspto,epo,cnipa"},
                    "limit": {"type": "string", "description": "最大结果数量"},
                },
                "required": ["query"],
            },
        },
        "handler": _handle_patent_search,
        "emoji": "🔎",
    },
    {
        "name": "similarity_analyzer",
        "schema": {
            "name": "similarity_analyzer",
            "description": "分析发明方案与现有技术的相似度，识别关键差异和风险",
            "parameters": {
                "type": "object",
                "properties": {
                    "invention": {"type": "string", "description": "待分析的发明技术方案"},
                    "prior_art": {"type": "string", "description": "对比的现有技术描述"},
                },
                "required": ["invention", "prior_art"],
            },
        },
        "handler": _handle_similarity_analyzer,
        "emoji": "⚖️",
    },
    {
        "name": "patentability_scorer",
        "schema": {
            "name": "patentability_scorer",
            "description": "评估技术方案的新颖性、创造性和实用性，给出综合专利性评分",
            "parameters": {
                "type": "object",
                "properties": {
                    "invention": {"type": "string", "description": "待评估的技术方案"},
                    "prior_art": {"type": "string", "description": "相关现有技术"},
                },
                "required": ["invention"],
            },
        },
        "handler": _handle_patentability_scorer,
        "emoji": "📊",
    },
    {
        "name": "claim_drafter",
        "schema": {
            "name": "claim_drafter",
            "description": "根据技术特征撰写独立权利要求和从属权利要求",
            "parameters": {
                "type": "object",
                "properties": {
                    "features": {"type": "string", "description": "技术特征列表或描述"},
                    "protection_scope": {"type": "string", "description": "期望的保护范围说明"},
                },
                "required": ["features"],
            },
        },
        "handler": _handle_claim_drafter,
        "emoji": "📝",
    },
    {
        "name": "description_writer",
        "schema": {
            "name": "description_writer",
            "description": "撰写专利说明书各章节(技术领域/背景/发明内容/具体实施方式)",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_type": {"type": "string", "description": "章节类型: technical_field/background/summary/drawings/detailed", "enum": ["technical_field", "background", "summary", "drawings", "detailed"]},
                    "technical_content": {"type": "string", "description": "该章节涉及的技术内容"},
                    "claims": {"type": "string", "description": "相关权利要求"},
                },
                "required": ["section_type", "technical_content"],
            },
        },
        "handler": _handle_description_writer,
        "emoji": "📄",
    },
    {
        "name": "terminology_normalizer",
        "schema": {
            "name": "terminology_normalizer",
            "description": "规范专利文件中的技术术语，确保全文一致性和专业性",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "需要规范化的文本"},
                    "domain": {"type": "string", "description": "技术领域"},
                },
                "required": ["text"],
            },
        },
        "handler": _handle_terminology_normalizer,
        "emoji": "📖",
    },
    {
        "name": "support_checker",
        "schema": {
            "name": "support_checker",
            "description": "检查权利要求与说明书之间的支持关系，识别支持性缺陷",
            "parameters": {
                "type": "object",
                "properties": {
                    "claims": {"type": "string", "description": "权利要求书内容"},
                    "description": {"type": "string", "description": "说明书内容"},
                },
                "required": ["claims", "description"],
            },
        },
        "handler": _handle_support_checker,
        "emoji": "🔗",
    },
    {
        "name": "compliance_checker",
        "schema": {
            "name": "compliance_checker",
            "description": "检查专利申请文件的格式和形式合规性",
            "parameters": {
                "type": "object",
                "properties": {
                    "patent_document": {"type": "string", "description": "专利文件内容"},
                },
                "required": ["patent_document"],
            },
        },
        "handler": _handle_compliance_checker,
        "emoji": "✅",
    },
    {
        "name": "claim_quality_analyzer",
        "schema": {
            "name": "claim_quality_analyzer",
            "description": "分析权利要求的清楚性、保护范围、层次结构等质量指标",
            "parameters": {
                "type": "object",
                "properties": {
                    "claims": {"type": "string", "description": "权利要求书完整内容"},
                },
                "required": ["claims"],
            },
        },
        "handler": _handle_claim_quality_analyzer,
        "emoji": "🎯",
    },
    {
        "name": "support_verifier",
        "schema": {
            "name": "support_verifier",
            "description": "验证说明书对权利要求的支持充分性(专利法第26条第4款)",
            "parameters": {
                "type": "object",
                "properties": {
                    "claims": {"type": "string", "description": "权利要求书内容"},
                    "description": {"type": "string", "description": "说明书内容"},
                },
                "required": ["claims", "description"],
            },
        },
        "handler": _handle_support_verifier,
        "emoji": "🔬",
    },
    {
        "name": "oa_predictor",
        "schema": {
            "name": "oa_predictor",
            "description": "预测专利审查中可能收到的审查意见，提供应对策略",
            "parameters": {
                "type": "object",
                "properties": {
                    "patent_document": {"type": "string", "description": "专利申请文件内容"},
                },
                "required": ["patent_document"],
            },
        },
        "handler": _handle_oa_predictor,
        "emoji": "⚠️",
    },
    {
        "name": "creative_thinking",
        "schema": {
            "name": "creative_thinking",
            "description": "基于技术方案激发创新思维，探索替代方案和拓展方向",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术发明描述"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_creative_thinking,
        "emoji": "✨",
    },
    {
        "name": "patent_strategy_guide",
        "schema": {
            "name": "patent_strategy_guide",
            "description": "基于技术方案和市场情况提供专利申请策略和保护策略建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术方案描述"},
                    "market_info": {"type": "string", "description": "市场和竞争信息"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_patent_strategy_guide,
        "emoji": "🎓",
    },
    {
        "name": "agent_selector",
        "schema": {
            "name": "agent_selector",
            "description": "根据任务描述选择最适合的专业Agent来处理任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "需要处理的任务描述"},
                    "exclude_agents": {"type": "string", "description": "排除的Agent ID(逗号分隔)"},
                },
                "required": ["task_description"],
            },
        },
        "handler": _handle_agent_selector,
        "emoji": "🤖",
    },
    {
        "name": "task_planner",
        "schema": {
            "name": "task_planner",
            "description": "制定专利申请的工作计划和时间线，分解任务，设定里程碑",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {"type": "string", "description": "技术发明描述"},
                    "patent_type": {"type": "string", "description": "专利类型: invention/utility_model"},
                    "priority": {"type": "string", "description": "优先级: high/medium/low"},
                },
                "required": ["tech_description"],
            },
        },
        "handler": _handle_task_planner,
        "emoji": "📋",
    },
    {
        "name": "quality_assessor",
        "schema": {
            "name": "quality_assessor",
            "description": "对专利申请文件进行质量评估，给出改进建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "document": {"type": "string", "description": "待评估的文件内容"},
                    "assessment_type": {"type": "string", "description": "评估类型"},
                },
                "required": ["document"],
            },
        },
        "handler": _handle_quality_assessor,
        "emoji": "🏆",
    },
    {
        "name": "report_generator",
        "schema": {
            "name": "report_generator",
            "description": "生成专利申请相关的各类报告(检索报告/分析报告/审查意见答复)",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string", "description": "报告类型"},
                    "content": {"type": "string", "description": "报告内容素材"},
                },
                "required": ["report_type", "content"],
            },
        },
        "handler": _handle_report_generator,
        "emoji": "📑",
    },
    {
        "name": "risk_analyzer",
        "schema": {
            "name": "risk_analyzer",
            "description": "分析专利申请过程中的各类风险(驳回/无效/侵权)",
            "parameters": {
                "type": "object",
                "properties": {
                    "patent_document": {"type": "string", "description": "专利相关文件"},
                    "risk_type": {"type": "string", "description": "风险类型"},
                },
                "required": ["patent_document"],
            },
        },
        "handler": _handle_risk_analyzer,
        "emoji": "⚡",
    },
    {
        "name": "prior_art_comparator",
        "schema": {
            "name": "prior_art_comparator",
            "description": "对比分析发明与多篇现有技术的技术特征差异，识别区别特征",
            "parameters": {
                "type": "object",
                "properties": {
                    "invention": {"type": "string", "description": "发明技术方案描述"},
                    "prior_arts": {"type": "string", "description": "现有技术列表（JSON格式或文本描述）"},
                },
                "required": ["invention", "prior_arts"],
            },
        },
        "handler": _handle_prior_art_comparator,
        "emoji": "📋",
    },
    {
        "name": "dispatch_specialist",
        "schema": {
            "name": "dispatch_specialist",
            "description": "调度专业Agent执行任务。CEO通过此工具将工作派发给专业Agent，每个Agent有独立专业知识。可用Agent: brainstorm_partner(讨论发散)、requirement_analyst(需求分析)、retrieval_analyst(先有技术检索)、patent_writer(专利撰写)、quality_reviewer(质量审查)",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID: brainstorm_partner/requirement_analyst/retrieval_analyst/patent_writer/quality_reviewer",
                        "enum": ["brainstorm_partner", "requirement_analyst", "retrieval_analyst", "patent_writer", "quality_reviewer"],
                    },
                    "task": {
                        "type": "string",
                        "description": "交给该Agent的具体任务描述，要清晰完整，包含所有必要上下文和期望输出格式",
                    },
                    "context": {
                        "type": "string",
                        "description": "附加上下文（前序阶段输出、用户补充信息、修改建议等）",
                    },
                },
                "required": ["agent_id", "task"],
            },
        },
        "handler": _handle_dispatch_specialist,
        "emoji": "🎯",
    },
    {
        "name": "patent_docx_generator",
        "schema": {
            "name": "patent_docx_generator",
            "description": "将结构化的专利撰写结果生成为符合专利局规范的.docx文件。在完成权利要求书和说明书撰写后调用此工具，输入结构化内容，输出格式规范的专利申请文件。文件格式：楷体14pt、首行缩进、A4页面、标准页边距、文档分节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "专利标题",
                    },
                    "claims": {
                        "type": "object",
                        "description": "权利要求书内容，格式: {\"independent_claim\": \"独立权利要求全文\", \"dependent_claims\": [\"从属权利要求1\", \"从属权利要求2\"]}",
                    },
                    "description": {
                        "type": "object",
                        "description": "说明书内容，格式: {\"technical_field\": \"技术领域\", \"background_art\": \"背景技术\", \"summary_of_invention\": \"发明内容\", \"description_of_drawings\": \"附图说明\", \"detailed_description\": \"具体实施方式\"}",
                    },
                    "abstract": {
                        "type": "string",
                        "description": "说明书摘要",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "任务ID，用于文件存储路径",
                    },
                },
                "required": ["title", "claims", "description", "abstract"],
            },
        },
        "handler": _handle_patent_docx_generator,
        "emoji": "📄",
    },
]


# ============ Registration ============

def register_patent_tools():
    """注册所有专利工具到 hermes-agent registry"""
    for tool_def in PATENT_TOOL_DEFINITIONS:
        handler = tool_def["handler"]
        # 包装 handler：每个工具结果自动写入临时文件，不依赖 LLM max_tokens
        saver = _make_temp_file_saver(tool_def["name"])
        wrapped_handler = saver(handler)
        registry.register(
            name=tool_def["name"],
            toolset="patent",
            schema=tool_def["schema"],
            handler=wrapped_handler,
            emoji=tool_def.get("emoji", "🔧"),
            description=tool_def["schema"].get("description", ""),
        )
    logger.info(f"Registered {len(PATENT_TOOL_DEFINITIONS)} patent tools to hermes-agent registry")


# 也需要在 toolsets.py 中注册 patent toolset
def register_patent_toolset():
    """将 patent toolset 注册到 hermes-agent 的 toolsets 系统"""
    from toolsets import TOOLSETS, create_custom_toolset
    if "patent" not in TOOLSETS:
        create_custom_toolset(
            name="patent",
            description="专利申请领域工具集 — IPC分类、检索、撰写、审查、策略",
            tools=[t["name"] for t in PATENT_TOOL_DEFINITIONS],
        )
    logger.info("Patent toolset registered in hermes-agent toolsets")


def init_patent_tools():
    """初始化专利工具（注册工具 + 注册工具集）"""
    register_patent_tools()
    register_patent_toolset()
