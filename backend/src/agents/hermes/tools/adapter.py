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


def _handle_transcript_sanitizer(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.transcript_sanitizer import TranscriptSanitizerTool
    tool = TranscriptSanitizerTool()
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


def _handle_patent_drawing_generator(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.patent_drawing_generator import PatentDrawingGeneratorTool
    tool = PatentDrawingGeneratorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_prior_art_comparator(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.prior_art_comparator import PriorArtComparatorTool
    tool = PriorArtComparatorTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_web_access_read_page(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.web_access import WebAccessReadPageTool
    tool = WebAccessReadPageTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_web_access_find_url(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.web_access import WebAccessFindUrlTool
    tool = WebAccessFindUrlTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_web_access_browser(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.web_access import WebAccessBrowserTool
    tool = WebAccessBrowserTool()
    result = _run_async(tool.execute(**args))
    return _json_result(result)


def _handle_web_access_match_site(args: Dict[str, Any], **kw) -> str:
    from src.agents.hermes.tools.web_access import WebAccessMatchSiteTool
    tool = WebAccessMatchSiteTool()
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
        "name": "transcript_sanitizer",
        "schema": {
            "name": "transcript_sanitizer",
            "description": "清洗交底逐字稿中的时间戳、说话人、会议格式和口语噪声，保留技术事实",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "原始技术交底文本或逐字稿内容"},
                },
                "required": ["text"],
            },
        },
        "handler": _handle_transcript_sanitizer,
        "emoji": "🧹",
    },
    {
        "name": "patent_search",
        "schema": {
            "name": "patent_search",
            "description": "在真实可用的多源专利数据库和公开资料源中检索相关现有技术",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询关键词或技术描述"},
                    "sources": {
                        "type": "string",
                        "description": "数据源(逗号分隔): google_patents,uspto,arxiv；留空使用全部可用真实数据源",
                    },
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
            "description": "提取发明方案与现有技术的相似术语、区别特征和客观风险信号；实质结论由 Agent 判断",
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
            "description": "提取技术方案与现有技术的术语重合、区别特征等客观信号；新颖性、创造性和实用性结论由 Agent 判断",
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
            "description": "提取权利要求与说明书之间的支持关系客观信号；是否构成支持性缺陷由 Agent 判断",
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
            "description": "执行可代码化的格式和形式硬规则检查；最终合规结论由质量审查 Agent 判断",
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
            "description": "提取权利要求清楚性、层次结构、换行和长度等客观信号；质量结论由 Agent 判断",
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
            "description": "提取说明书对权利要求支持关系的客观信号；充分性结论由 Agent 判断",
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
            "description": "检查可能触发审查意见的客观文本信号；是否构成 OA 风险及应对策略由 Agent 判断",
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
            "description": "根据技术文本提取可供 Agent 发散的候选方向；创新价值和采用与否由 Agent 判断",
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
            "description": "根据技术文本整理申请策略候选项和检查清单；最终申请策略由 Agent 判断",
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
            "description": "根据技术文本生成候选工作拆解和里程碑；最终计划由 CEO Agent 调度确认",
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
            "description": "提取专利申请文件的结构、完整性、格式和明显缺失等客观信号；质量判断和改进建议由 Agent 完成",
            "parameters": {
                "type": "object",
                "properties": {
                    "phase_name": {"type": "string", "description": "阶段名称: requirement/retrieval/writing/review"},
                    "output_content": {"type": "string", "description": "该阶段的输出内容(JSON或文本)"},
                    "requirements": {"type": "string", "description": "需要硬规则检查的格式/结构要求"},
                },
                "required": ["phase_name", "output_content"],
            },
        },
        "handler": _handle_quality_assessor,
        "emoji": "🏆",
    },
    {
        "name": "report_generator",
        "schema": {
            "name": "report_generator",
            "description": "根据已确认素材整理报告草稿；报告结论和取舍由对应 Agent 判断",
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
            "description": "提取驳回、无效、侵权等方向的客观风险信号；风险等级和处理策略由 Agent 判断",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {"type": "string", "description": "分析类型: novelty/inventive_step/prior_art/support/overall"},
                    "tech_data": {"type": "string", "description": "技术数据、专利文件或检索证据"},
                    "prior_art_references": {"type": "string", "description": "现有技术参考列表(JSON或文本)"},
                },
                "required": ["analysis_type", "tech_data"],
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
        "name": "web_access_read_page",
        "schema": {
            "name": "web_access_read_page",
            "description": "运行 web-access 前置检查，并可选打开页面返回基础信息与 DOM eval 结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "可选。需要后台打开的页面 URL"},
                    "browser": {"type": "string", "description": "可选。一次性指定浏览器 chrome 或 edge", "enum": ["chrome", "edge"]},
                    "eval_expression": {"type": "string", "description": "可选。打开后执行的 JS 表达式"},
                    "auto_close": {"type": "string", "description": "可选。默认 true，读取后关闭新建 tab"},
                },
                "required": [],
            },
        },
        "handler": _handle_web_access_read_page,
        "emoji": "🌐",
    },
    {
        "name": "web_access_find_url",
        "schema": {
            "name": "web_access_find_url",
            "description": "通过 web-access 的 find-url.mjs 查询本地 Chrome 书签与历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "可选。空格分词关键字"},
                    "only": {"type": "string", "description": "可选。bookmarks 或 history", "enum": ["bookmarks", "history"]},
                    "browser": {"type": "string", "description": "可选。限定浏览器 chrome 或 edge", "enum": ["chrome", "edge"]},
                    "limit": {"type": "string", "description": "可选。结果上限，默认 20"},
                    "since": {"type": "string", "description": "可选。1d / 7h / YYYY-MM-DD"},
                    "sort": {"type": "string", "description": "可选。recent 或 visits", "enum": ["recent", "visits"]},
                },
                "required": [],
            },
        },
        "handler": _handle_web_access_find_url,
        "emoji": "🔗",
    },
    {
        "name": "web_access_browser",
        "schema": {
            "name": "web_access_browser",
            "description": "通过 web-access CDP Proxy 执行 tab 管理、导航、DOM eval、交互、截图与健康检查",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "代理操作",
                        "enum": ["health", "targets", "new", "navigate", "back", "info", "eval", "click", "clickAt", "setFiles", "scroll", "screenshot", "close", "preflight"],
                    },
                    "target": {"type": "string", "description": "目标 tab 的 targetId"},
                    "url": {"type": "string", "description": "new/navigate 使用的 URL"},
                    "browser": {"type": "string", "description": "可选。preflight 时一次性指定浏览器 chrome 或 edge", "enum": ["chrome", "edge"]},
                    "expression": {"type": "string", "description": "eval 使用的 JS 表达式"},
                    "selector": {"type": "string", "description": "click/clickAt/setFiles 使用的 CSS selector"},
                    "files_json": {"type": "string", "description": "setFiles 用 JSON 字符串，如 [\"/tmp/a.png\"]"},
                    "file_path": {"type": "string", "description": "screenshot 输出路径；缺省时自动生成临时文件"},
                    "y": {"type": "string", "description": "scroll 像素值"},
                    "direction": {"type": "string", "description": "scroll 方向 down/up/top/bottom"},
                    "format": {"type": "string", "description": "截图格式 png/jpeg", "enum": ["png", "jpeg"]},
                },
                "required": ["action"],
            },
        },
        "handler": _handle_web_access_browser,
        "emoji": "🧭",
    },
    {
        "name": "web_access_match_site",
        "schema": {
            "name": "web_access_match_site",
            "description": "根据查询内容匹配 bundled web-access 的站点经验文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "需要匹配站点经验的查询文本"},
                },
                "required": ["query"],
            },
        },
        "handler": _handle_web_access_match_site,
        "emoji": "🗂️",
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
        "name": "patent_drawing_generator",
        "schema": {
            "name": "patent_drawing_generator",
            "description": "根据技术方案生成专利说明书附图，使用撰写Agent生图配置或系统生图配置并返回附图元数据。需要附图时必须在质量审查和生成DOCX前调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_description": {
                        "type": "string",
                        "description": "专利整体技术方案背景，仅用于辅助理解附图内容",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "任务ID，用于将附图保存到对应工作流导出目录",
                    },
                    "title": {
                        "type": "string",
                        "description": "该图在说明书中的附图标题",
                    },
                    "description": {
                        "type": "string",
                        "description": "必填。该图必须绘制的具体内容，包括对象、模块/步骤/结构、连接关系、箭头方向、编号和本图与其他图的区别。必须来自当前专利真实内容，工具不会套用内置模板。",
                    },
                    "figure_number": {
                        "type": "string",
                        "description": "附图编号，例如：图1、图2、图3。生成多张附图时必须分别调用并传入对应编号。",
                    },
                },
                "required": ["tech_description", "task_id", "description"],
            },
        },
        "handler": _handle_patent_drawing_generator,
        "emoji": "🖼️",
    },
    {
        "name": "patent_docx_generator",
        "schema": {
            "name": "patent_docx_generator",
            "description": "将结构化的专利撰写结果生成为符合专利局规范的.docx文件。在质量审查通过后调用此工具，输入权利要求、说明书、摘要以及 patent_drawing_generator 已生成的 drawings 元数据，输出格式规范的专利申请文件。",
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
                    "tech_description": {
                        "type": "string",
                        "description": "清洗后的技术方案描述，仅用于生成文档元数据和上下文；不得替代 drawings 附图元数据。",
                    },
                    "drawings": {
                        "type": "array",
                        "description": "patent_drawing_generator 返回的附图元数据列表，用于插入摘要附图和说明书附图。",
                        "items": {"type": "object"},
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
