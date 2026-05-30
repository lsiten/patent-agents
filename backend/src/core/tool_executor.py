"""
Tool Executor — 应用层主动工具调用模块

由于代理服务器不支持 OpenAI tools 参数传递，此模块在 workflow_engine 中
主动调用工具，并将结果作为上下文传递给 Agent。

工作流程：
1. 在每个阶段开始前，根据阶段类型调用对应工具
2. 收集工具返回结果
3. 将工具结果作为上下文传递给 Agent
4. Agent 基于真实工具数据生成分析结论
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolExecutor:
    """应用层工具执行器"""
    
    def __init__(self):
        self._tool_handlers: Dict[str, Callable] = {}
        self._load_tool_handlers()
    
    def _load_tool_handlers(self):
        """加载所有工具处理器"""
        try:
            from src.agents.hermes.tools.adapter import PATENT_TOOL_DEFINITIONS
            for tool_def in PATENT_TOOL_DEFINITIONS:
                name = tool_def["name"]
                handler = tool_def["handler"]
                self._tool_handlers[name] = handler
            logger.info(f"ToolExecutor loaded {len(self._tool_handlers)} tool handlers")
        except Exception as e:
            logger.error(f"Failed to load tool handlers: {e}")
    
    def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        event_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        执行单个工具
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            event_callback: 事件回调函数
            
        Returns:
            工具执行结果
        """
        handler = self._tool_handlers.get(tool_name)
        if not handler:
            logger.warning(f"Unknown tool: {tool_name}")
            return {
                "tool": tool_name,
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "data": None,
            }
        
        start_time = datetime.now()
        
        # 发射工具开始事件
        if event_callback:
            event_callback("工具执行器", "agent.tool_call_start", 
                f"🔧 调用工具: {tool_name}",
                {"tool_name": tool_name, "parameters": args})
        
        try:
            logger.info(f"Executing tool: {tool_name} with args: {str(args)[:200]}")
            result_str = handler(args)
            
            # 解析结果
            if isinstance(result_str, str):
                # 移除可能的文件路径后缀
                if "[TOOL_OUTPUT_SAVED_TO]:" in result_str:
                    result_str = result_str.split("[TOOL_OUTPUT_SAVED_TO]:")[0].strip()
                try:
                    result_data = json.loads(result_str)
                except json.JSONDecodeError:
                    result_data = {"raw_output": result_str}
            else:
                result_data = result_str
            
            duration = (datetime.now() - start_time).total_seconds()
            
            tool_result = {
                "tool": tool_name,
                "success": True,
                "error": None,
                "data": result_data,
                "duration_seconds": duration,
                "timestamp": datetime.now().isoformat(),
            }
            
            # 发射工具完成事件
            if event_callback:
                result_preview = str(result_data)[:200]
                event_callback("工具执行器", "agent.tool_call_end",
                    f"✅ {tool_name} 完成 ({duration:.1f}s): {result_preview}",
                    {"tool_name": tool_name, "result": result_preview, "success": True})
            
            logger.info(f"Tool {tool_name} completed in {duration:.1f}s")
            return tool_result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Tool {tool_name} failed: {e}")
            
            tool_result = {
                "tool": tool_name,
                "success": False,
                "error": str(e),
                "data": None,
                "duration_seconds": duration,
                "timestamp": datetime.now().isoformat(),
            }
            
            if event_callback:
                event_callback("工具执行器", "agent.tool_call_end",
                    f"❌ {tool_name} 失败: {str(e)[:100]}",
                    {"tool_name": tool_name, "error": str(e), "success": False})
            
            return tool_result
    
    async def execute_tools_for_phase(
        self,
        phase: str,
        context: Dict[str, Any],
        event_callback: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        为指定阶段执行所有必需工具
        
        Args:
            phase: 阶段名称 (requirement_analysis, retrieval_analysis, patent_writing, quality_review)
            context: 上下文数据
            event_callback: 事件回调
            
        Returns:
            工具执行结果列表
        """
        tool_results = []
        
        tech_description = context.get("tech_description", "")
        requirement_analysis = context.get("requirement_analysis", {})
        retrieval_report = context.get("retrieval_report", {})
        patent_draft = context.get("patent_draft", {})
        
        if phase == "requirement_analysis":
            # 需求分析阶段：调用 IPC 分类、技术特征提取、场景挖掘
            tools_to_call = [
                ("ipc_classifier", {"tech_description": tech_description}),
                ("tech_feature_extractor", {"tech_description": tech_description}),
                ("scenario_miner", {"tech_description": tech_description, "features": ""}),
            ]
            
        elif phase == "retrieval_analysis":
            # 检索分析阶段：调用专利检索、相似度分析、专利性评分、风险分析
            # 从需求分析中提取关键词
            keywords = []
            if isinstance(requirement_analysis, dict):
                features = requirement_analysis.get("key_innovative_features", [])
                if isinstance(features, list):
                    for f in features:
                        if isinstance(f, dict):
                            keywords.append(f.get("name", "") or f.get("feature_name", ""))
                        elif isinstance(f, str):
                            keywords.append(f)
                keywords.append(requirement_analysis.get("tech_field", ""))
            
            query = tech_description[:500] + " " + " ".join(keywords[:5])
            
            tools_to_call = [
                ("patent_search", {"query": query, "sources": "cnipa,uspto,epo", "limit": "10"}),
                ("similarity_analyzer", {"invention": tech_description, "prior_art": "基于检索结果的现有技术"}),
                ("patentability_scorer", {"invention": tech_description, "prior_art": ""}),
                ("risk_analyzer", {"patent_document": tech_description, "risk_type": "all"}),
            ]
            
        elif phase == "patent_writing":
            # 专利撰写阶段：调用权利要求撰写、说明书撰写、支持性检查
            features_str = ""
            if isinstance(requirement_analysis, dict):
                features = requirement_analysis.get("key_innovative_features", [])
                if isinstance(features, list):
                    features_str = json.dumps(features, ensure_ascii=False)
            
            tools_to_call = [
                ("claim_drafter", {"features": features_str or tech_description, "protection_scope": ""}),
                ("description_writer", {"section_type": "technical_field", "technical_content": tech_description}),
                ("description_writer", {"section_type": "background", "technical_content": tech_description}),
                ("description_writer", {"section_type": "summary", "technical_content": tech_description, "claims": ""}),
                ("description_writer", {"section_type": "detailed", "technical_content": tech_description, "claims": ""}),
            ]
            
        elif phase == "quality_review":
            # 质量审查阶段：调用合规检查、权利要求质量分析、支持性验证、审查意见预测
            patent_doc = json.dumps(patent_draft, ensure_ascii=False) if isinstance(patent_draft, dict) else str(patent_draft)
            claims = ""
            description = ""
            if isinstance(patent_draft, dict):
                claims_obj = patent_draft.get("claims", {})
                if isinstance(claims_obj, dict):
                    claims = claims_obj.get("independent_claim", "") + "\n" + "\n".join(claims_obj.get("dependent_claims", []))
                desc_obj = patent_draft.get("description", {})
                if isinstance(desc_obj, dict):
                    description = json.dumps(desc_obj, ensure_ascii=False)
            
            tools_to_call = [
                ("compliance_checker", {"patent_document": patent_doc[:5000]}),
                ("claim_quality_analyzer", {"claims": claims or patent_doc[:3000]}),
                ("support_verifier", {"claims": claims or "", "description": description or patent_doc[:3000]}),
                ("oa_predictor", {"patent_document": patent_doc[:5000]}),
            ]
            
        else:
            logger.warning(f"Unknown phase for tool execution: {phase}")
            return []
        
        # 执行工具
        for tool_name, args in tools_to_call:
            result = await asyncio.to_thread(
                self.execute_tool, tool_name, args, event_callback
            )
            tool_results.append(result)
        
        logger.info(f"Phase {phase}: executed {len(tool_results)} tools, "
                   f"{sum(1 for r in tool_results if r['success'])} succeeded")
        
        return tool_results
    
    def format_tool_results_for_prompt(self, tool_results: List[Dict[str, Any]]) -> str:
        """
        将工具结果格式化为可嵌入 prompt 的文本
        
        Args:
            tool_results: 工具执行结果列表
            
        Returns:
            格式化的文本
        """
        if not tool_results:
            return ""
        
        lines = ["## 工具调用结果（请基于以下数据进行分析）\n"]
        
        for result in tool_results:
            tool_name = result.get("tool", "unknown")
            success = result.get("success", False)
            
            if success:
                data = result.get("data", {})
                # 提取关键数据
                if isinstance(data, dict):
                    data_preview = json.dumps(data, ensure_ascii=False, indent=2)[:2000]
                else:
                    data_preview = str(data)[:2000]
                lines.append(f"### {tool_name} ✅\n```json\n{data_preview}\n```\n")
            else:
                error = result.get("error", "Unknown error")
                lines.append(f"### {tool_name} ❌\n错误: {error}\n")
        
        return "\n".join(lines)


# 全局单例
_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    """获取全局工具执行器实例"""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor
