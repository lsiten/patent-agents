"""
Dispatch Specialist Tool — CEO Agent 动态调度专业 Agent

允许 CEO Agent 在运行时动态选择并调用具有完整 Profile（SOUL.md + skills + toolset）
的专业 Agent，实现动态编排而非固定流水线。

与 hermes-agent 内置的 delegate_task 不同：
- delegate_task: spawn 通用 subagent（无 profile 特性）
- dispatch_specialist: 调用有完整 SOUL.md + 专业技能的 Profile Agent

使用场景：
- CEO 判断搜索结果不足 → dispatch retrieval_analyst 补充检索
- CEO 判断撰写质量不达标 → 分析原因 → dispatch 回对应阶段
- CEO 判断需要更多讨论 → dispatch brainstorm_partner
"""
import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter

logger = logging.getLogger(__name__)

# ============ 父级对话上下文（线程安全） ============
# dispatch_specialist 创建的 sub-agent 需要访问父级（CEO）的对话上下文。
# 使用 threading.local() 确保每个线程有独立的上下文副本，避免并发请求间的竞态条件。
# routes.py 在调用 CEO agent 前 set_parent_context()，dispatch_specialist 内部自动读取并注入。

_thread_local = threading.local()


def set_parent_context(context: str) -> None:
    """设置当前线程的父级对话上下文（routes.py 在调用 CEO 前调用）"""
    _thread_local.parent_context = context


def get_parent_context() -> str:
    """获取当前线程的父级对话上下文"""
    return getattr(_thread_local, "parent_context", "")


def clear_parent_context() -> None:
    """清理当前线程的父级对话上下文"""
    if hasattr(_thread_local, "parent_context"):
        delattr(_thread_local, "parent_context")


def set_parent_callbacks(callbacks: Optional[Dict[str, Any]]) -> None:
    """设置当前线程的父级回调，供子 Agent 将实时事件回传给父流。"""
    _thread_local.parent_callbacks = callbacks or {}


def get_parent_callbacks() -> Dict[str, Any]:
    """获取当前线程的父级回调。"""
    return getattr(_thread_local, "parent_callbacks", {})


def clear_parent_callbacks() -> None:
    """清理当前线程的父级回调。"""
    if hasattr(_thread_local, "parent_callbacks"):
        delattr(_thread_local, "parent_callbacks")


def clear_parent_state() -> None:
    """清理当前线程的父级上下文和回调。"""
    clear_parent_context()
    clear_parent_callbacks()

# 可调度的专业 Agent 列表
SPECIALIST_AGENTS = {
    "brainstorm_partner": {
        "profile_id": "patent.brainstorm_partner.v1",
        "name": "头脑风暴伙伴",
        "description": "帮助梳理发明思路、拓展保护方向、探讨技术细节",
        "use_when": "需要与用户讨论技术方案、澄清细节、发散思维时",
        "phase": "brainstorming",
    },
    "requirement_analyst": {
        "profile_id": "patent.requirement_analyst.v1",
        "name": "需求分析师",
        "description": "将技术描述转化为结构化专利需求（技术领域、创新点、IPC分类）",
        "use_when": "需要结构化分析技术方案、提取创新点、确定专利类型时",
        "phase": "requirement_analysis",
    },
    "retrieval_analyst": {
        "profile_id": "patent.retrieval_analyst.v1",
        "name": "检索分析师",
        "description": "检索先有技术、评估专利性（新颖性/创造性/实用性）、识别风险",
        "use_when": "需要检索现有技术、评估专利性、对比分析差异时",
        "phase": "retrieval_report",
    },
    "patent_writer": {
        "profile_id": "patent.writer.v1",
        "name": "专利撰写师",
        "description": "撰写权利要求书、说明书、摘要等完整专利申请文件",
        "use_when": "需要撰写或修改专利申请文件时",
        "phase": "patent_draft",
    },
    "quality_reviewer": {
        "profile_id": "patent.quality_reviewer.v1",
        "name": "质量审查师",
        "description": "审查专利文件质量（形式合规、权利要求、说明书、一致性、审查风险）",
        "use_when": "需要对已撰写的专利文件进行质量审查时",
        "phase": "review_report",
    },
}


# ============ 全局结果缓存 ============
# 存储各 Agent 的实际输出，供 workflow_engine 读取

_dispatch_results: List[Dict[str, Any]] = []


def get_dispatch_results() -> List[Dict[str, Any]]:
    """获取所有 dispatch 结果"""
    return list(_dispatch_results)


def clear_dispatch_results() -> None:
    """清空结果缓存（workflow 开始时调用）"""
    _dispatch_results.clear()


def get_latest_result_by_phase(phase: str) -> Optional[Dict[str, Any]]:
    """获取某阶段的最新结果"""
    for r in reversed(_dispatch_results):
        if r.get("phase") == phase:
            return r
    return None


class DispatchSpecialistTool(HermesTool):
    """动态调度专业 Agent 工具"""

    name = "dispatch_specialist"
    description = (
        "调度一个专业 Agent 执行特定任务。每个 Agent 有独立的专业知识和工具集。"
        "可用 Agent: brainstorm_partner(讨论)、requirement_analyst(需求分析)、"
        "retrieval_analyst(检索分析)、patent_writer(撰写)、quality_reviewer(审查)"
    )

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "agent_id": HermesToolParameter(
                    type="string",
                    description=(
                        "要调度的 Agent ID。可选值: "
                        "brainstorm_partner, requirement_analyst, "
                        "retrieval_analyst, patent_writer, quality_reviewer"
                    ),
                    required=True,
                ),
                "task": HermesToolParameter(
                    type="string",
                    description="交给该 Agent 的具体任务描述，要清晰完整，包含所有必要上下文",
                    required=True,
                ),
                "context": HermesToolParameter(
                    type="string",
                    description="附加上下文（前序阶段的输出、用户补充信息等）",
                    required=False,
                ),
            },
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        agent_id = kwargs.get("agent_id", "")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")

        # 验证 agent_id
        if agent_id not in SPECIALIST_AGENTS:
            return {
                "error": f"未知的 Agent: {agent_id}",
                "available_agents": list(SPECIALIST_AGENTS.keys()),
            }

        if not task.strip():
            return {"error": "task 参数不能为空"}

        specialist = SPECIALIST_AGENTS[agent_id]
        profile_id = specialist["profile_id"]
        phase = specialist["phase"]

        # 注入父级对话上下文（routes.py 通过 set_parent_context 设置）
        parent_ctx = get_parent_context()
        context_parts = []
        if context:
            context_parts.append(f"【上下文信息】\n{context}")
        if parent_ctx:
            context_parts.append(f"【用户对话历史】\n{parent_ctx}")

        full_prompt = task
        if context_parts:
            full_prompt = f"{task}\n\n" + "\n\n".join(context_parts)

        logger.info(
            f"[dispatch_specialist] CEO → {specialist['name']} ({profile_id}): {task[:80]}..."
        )

        try:
            from src.agents.agent_config import create_ai_agent

            parent_callbacks = get_parent_callbacks()
            parent_activity = parent_callbacks.get("agent_activity")
            child_callbacks: Optional[Dict[str, Any]] = None

            if callable(parent_activity):
                base_data = {
                    "agent_id": agent_id,
                    "agent_name": specialist["name"],
                    "profile_id": profile_id,
                }

                def forward_activity(
                    event_type: str,
                    message: str,
                    data: Optional[Dict[str, Any]] = None,
                    call_id: Optional[str] = None,
                ) -> None:
                    payload = {**base_data, **(data or {})}
                    parent_activity(
                        event_type=event_type,
                        message=message,
                        data=payload,
                        call_id=call_id,
                        agent_name=specialist["name"],
                    )

                def on_thinking(text: Any) -> None:
                    thought = str(text).strip() if text else ""
                    if thought:
                        forward_activity(
                            "thinking",
                            thought[:300],
                            {"message": thought[:300]},
                        )

                def on_status(kind: Any, message: Any) -> None:
                    status_message = str(message).strip() if message else ""
                    if status_message:
                        forward_activity(
                            "status",
                            status_message[:300],
                            {"kind": str(kind), "message": status_message[:300]},
                        )

                def on_tool_start(call_id: Any, name: Any, args: Any) -> None:
                    params: Dict[str, Any] = {}
                    if isinstance(args, str):
                        try:
                            params = json.loads(args)
                        except Exception:
                            params = {"raw": args[:200]}
                    elif isinstance(args, dict):
                        params = args
                    tool_name = str(name)
                    forward_activity(
                        "tool_call_start",
                        f"调用工具: {tool_name}",
                        {"name": tool_name, "parameters": params},
                        str(call_id),
                    )

                def on_tool_complete(call_id: Any, name: Any, args: Any, result: Any) -> None:
                    tool_name = str(name)
                    result_text = str(result)[:500] if result else ""
                    forward_activity(
                        "tool_call_end",
                        f"工具完成: {tool_name}",
                        {"name": tool_name, "result": result_text, "success": True},
                        str(call_id),
                    )

                child_callbacks = {
                    "thinking": on_thinking,
                    "status": on_status,
                    "tool_start": on_tool_start,
                    "tool_complete": on_tool_complete,
                }

            agent = create_ai_agent(profile_id=profile_id, callbacks=child_callbacks)
            # AIAgent.run_conversation 是同步的，需要在线程中运行
            result = await asyncio.to_thread(agent.run_conversation, full_prompt)

            # 归一化结果为字符串
            if isinstance(result, dict):
                result_text = result.get("final_response", "") or result.get("content", "") or json.dumps(result, ensure_ascii=False)
            else:
                result_text = str(result) if result else ""

            logger.info(
                f"[dispatch_specialist] {specialist['name']} 完成，结果长度: {len(result_text)} chars"
            )

            # 存储到全局缓存（供 workflow_engine 读取）
            dispatch_record = {
                "agent": specialist["name"],
                "agent_id": agent_id,
                "profile_id": profile_id,
                "phase": phase,
                "task": task[:500],
                "result": result_text,
                "status": "completed",
            }
            _dispatch_results.append(dispatch_record)

            return {
                "agent": specialist["name"],
                "agent_id": agent_id,
                "profile_id": profile_id,
                "task": task[:200],
                "result": result_text,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"[dispatch_specialist] {specialist['name']} 执行失败: {e}")
            error_record = {
                "agent": specialist["name"],
                "agent_id": agent_id,
                "profile_id": profile_id,
                "phase": phase,
                "task": task[:500],
                "error": str(e),
                "status": "failed",
            }
            _dispatch_results.append(error_record)

            return {
                "agent": specialist["name"],
                "agent_id": agent_id,
                "error": str(e),
                "status": "failed",
            }
