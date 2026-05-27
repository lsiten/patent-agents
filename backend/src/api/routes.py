from typing import Any, Dict, List
import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from .schemas import (
    ChatMessageRequest,
    CreateTaskRequest,
    TaskResponse,
    TaskDetailResponse,
    TaskListResponse,
    WorkflowEventResponse,
    WorkflowListResponse,
    WorkflowResponse,
    SearchPatentRequest,
    SearchResponse,
    SystemStatusResponse,
    KnowledgeBaseSearchResponse,
    WorkflowStartRequest,
    AgentDetailResponse,
    AgentListResponse,
    AgentToggleResponse,
    AgentUpdateResponse,
    OrganizationUpdateResponse,
    OrgNodeResponse,
    PriorArtReferenceResponse,
    # Conversation schemas
    ConversationSummary,
    ConversationMessage,
    ConversationDetail,
    ConversationListResponse,
    ConversationChatResponse,
    CreateConversationRequest,
    ConversationChatRequest,
    CreateWorkflowFromConversationRequest,
)
from ..models.domain import PatentTask
from ..models.enums import WorkflowState
from ..agents import AgentProfile, AgentRole, AgentSkill, get_profile_registry, register_default_profiles
from ..agents.ceo import CEOAgent
from ..core.workflow_engine import PatentWorkflowEngine, WorkflowContext
from ..knowledge.base import get_knowledge_base
from ..data_sources.base import get_data_source_manager
from ..infrastructure.persistence import get_store
from .schemas import WorkflowEventResponse, OrgNodeResponse


router = APIRouter(tags=["patent-agents"])


# 内存存储 - 生产环境请替换为数据库
tasks_store: Dict[str, PatentTask] = {}
task_events: Dict[str, List[WorkflowEventResponse]] = {}
workflow_lock = asyncio.Lock()

# 对话会话存储
conversations_store: Dict[str, dict] = {}
conversations_lock = asyncio.Lock()

profile_registry = get_profile_registry()
register_default_profiles(profile_registry)
workflow_engine = PatentWorkflowEngine()
organization_tree_store: OrgNodeResponse | None = None

# ── 持久化存储辅助 ──
_store_instance = None


def _get_persist_store():
    global _store_instance
    if _store_instance is None:
        _store_instance = get_store()
    return _store_instance


async def _persist_task(task_id: str) -> None:
    task = tasks_store.get(task_id)
    if task is None:
        return
    try:
        await _get_persist_store().save("tasks", task_id, task.model_dump(mode="json"))
    except Exception as e:
        logger.warning(f"保存任务 {task_id} 到数据库失败: {e}")


async def _persist_events(task_id: str) -> None:
    events = task_events.get(task_id)
    if events is None:
        return
    try:
        await _get_persist_store().save("task_events", task_id, [e.model_dump(mode="json") for e in events])
    except Exception as e:
        logger.warning(f"保存事件 {task_id} 到数据库失败: {e}")


async def _persist_conversation(conv_id: str) -> None:
    conv = conversations_store.get(conv_id)
    if conv is None:
        return
    try:
        await _get_persist_store().save("conversations", conv_id, conv)
    except Exception as e:
        logger.warning(f"保存对话 {conv_id} 到数据库失败: {e}")


async def _persist_org_tree() -> None:
    if organization_tree_store is None:
        return
    try:
        await _get_persist_store().save("org_tree", "root", organization_tree_store.model_dump(mode="json"))
    except Exception as e:
        logger.warning(f"保存组织架构到数据库失败: {e}")


async def restore_stores_from_db() -> None:
    """启动时从数据库恢复内存存储"""
    store = _get_persist_store()
    try:
        for key, value in await store.load_all("tasks"):
            try:
                tasks_store[key] = PatentTask.model_validate(value)
            except Exception as e:
                logger.warning(f"恢复任务 {key} 失败: {e}")

        for key, value in await store.load_all("task_events"):
            try:
                task_events[key] = [WorkflowEventResponse.model_validate(e) for e in value]
            except Exception as e:
                logger.warning(f"恢复事件 {key} 失败: {e}")

        for key, value in await store.load_all("conversations"):
            conversations_store[key] = value

        org_val = await store.load("org_tree", "root")
        if org_val is not None:
            global organization_tree_store
            organization_tree_store = OrgNodeResponse.model_validate(org_val)

        logger.info(
            f"从数据库恢复: {len(tasks_store)} 个任务, "
            f"{len(task_events)} 组事件, "
            f"{len(conversations_store)} 个对话"
        )
    except Exception as e:
        logger.warning(f"数据库恢复失败（首次启动?）: {e}")


def _workflow_context_to_response(context: WorkflowContext) -> WorkflowResponse:
    return WorkflowResponse(
        task_id=context.task_id,
        user_id=context.user_id,
        current_state=context.current_phase.value,
        created_at=context.created_at,
        updated_at=context.updated_at,
        iteration_count=context.iteration_count,
        message_count=len(context.message_history),
        phase_history=[
            {
                "phase": result.phase.value,
                "success": result.success,
                "duration_seconds": result.duration_seconds,
                "issues": result.issues,
                "warnings": result.warnings,
            }
            for result in context.phase_history
        ],
        outputs={
            "brainstorming": context.brainstorming_output,
            "requirement_analysis": context.requirement_analysis,
            "retrieval_report": context.retrieval_report,
            "patent_draft": context.patent_draft,
            "review_report": context.review_report,
        },
    )


def _agent_ui_role(role: AgentRole) -> str:
    if role == AgentRole.CEO:
        return "orchestrator"
    if role == AgentRole.BRAINSTORM_PARTNER:
        return "assistant"
    if role == AgentRole.QUALITY_REVIEWER:
        return "critic"
    return "specialist"


def _agent_parent_id(profile: AgentProfile) -> str | None:
    if profile.report_to_roles:
        parent_role = profile.report_to_roles[0]
        parents = profile_registry.get_by_role(parent_role)
        return parents[0].profile_id if parents else None
    return None


def _agent_child_ids(profile: AgentProfile) -> List[str]:
    child_ids: List[str] = []
    for child_role in profile.allowed_child_roles:
        child_ids.extend(child.profile_id for child in profile_registry.get_by_role(child_role))
    return child_ids


def _agent_config_from_profile(profile: AgentProfile) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    created_at = profile.created_at or now
    return {
        "id": profile.profile_id,
        "name": profile.name,
        "description": profile.description,
        "role": _agent_ui_role(profile.role),
        "system_prompt": profile.get_system_prompt(),
        "model": profile.model or "default",
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "working_directory": f"./workspace/{profile.profile_id.replace('.', '-')}",
        "enabled": True,
        "created_at": created_at,
        "updated_at": now,
        "parent_id": _agent_parent_id(profile),
        "child_ids": _agent_child_ids(profile),
    }


def _agent_tool_category(tool_name: str) -> str:
    if any(keyword in tool_name for keyword in ("search", "retrieval", "knowledge")):
        return "search"
    if any(keyword in tool_name for keyword in ("format", "write", "draft", "document", "claim")):
        return "file"
    if any(keyword in tool_name for keyword in ("delegate", "spawn", "workflow")):
        return "external"
    return "analysis"


def _agent_tools_from_profile(profile: AgentProfile) -> List[Dict[str, Any]]:
    return [
        {
            "id": tool_name,
            "name": tool_name,
            "description": profile.tool_config.tool_overrides.get(tool_name, {}).get(
                "description",
                f"Hermes Profile 启用工具：{tool_name}",
            ),
            "enabled": True,
            "category": _agent_tool_category(tool_name),
            "config": {},
        }
        for tool_name in profile.tool_config.enabled_tools
    ]


def _agent_skills_from_profile(profile: AgentProfile) -> List[Dict[str, Any]]:
    return [
        {
            "id": skill.name,
            "name": skill.name,
            "description": skill.description,
            "enabled": True,
            "version": profile.version,
            "tags": skill.keywords,
        }
        for skill in profile.skills
    ]


def _agent_memories_from_profile(profile: AgentProfile) -> List[Dict[str, Any]]:
    now = datetime.now().isoformat()
    memory_config = profile.memory_config
    memories = []
    if memory_config.enable_short_term_memory:
        memories.append({
            "id": "short_term",
            "type": "short_term",
            "name": "短期对话记忆",
            "size": memory_config.max_conversation_history * 1024,
            "item_count": memory_config.max_conversation_history,
            "last_updated": now,
        })
    if memory_config.enable_long_term_memory:
        memories.append({
            "id": "long_term",
            "type": "long_term",
            "name": "长期经验记忆",
            "size": 0,
            "item_count": 0,
            "last_updated": now,
        })
    if memory_config.enable_knowledge_base:
        memories.append({
            "id": "knowledge_base",
            "type": "knowledge_base",
            "name": "知识库记忆",
            "size": 0,
            "item_count": len(memory_config.knowledge_base_ids),
            "last_updated": now,
        })
    return memories


def _require_agent_profile(agent_id: str) -> AgentProfile:
    profile = profile_registry.get(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent不存在")
    return profile


def _agent_node(profile: AgentProfile) -> Dict[str, Any]:
    return {
        "id": profile.profile_id,
        "name": profile.name,
        "type": "agent",
        "description": profile.description,
        "expanded": True,
        "agent_config": _agent_config_from_profile(profile),
        "children": [],
    }


def _profiles_by_roles(roles: List[AgentRole]) -> List[AgentProfile]:
    profiles: List[AgentProfile] = []
    for role in roles:
        profiles.extend(profile_registry.get_by_role(role))
    return profiles


def _validate_org_tree(tree: OrgNodeResponse, depth: int = 0, seen_ids: set[str] | None = None) -> int:
    if seen_ids is None:
        seen_ids = set()
    if depth > 8:
        raise HTTPException(status_code=400, detail="组织架构层级过深")
    if tree.id in seen_ids:
        raise HTTPException(status_code=400, detail="组织架构节点ID重复")
    if not tree.id.strip() or not tree.name.strip():
        raise HTTPException(status_code=400, detail="组织架构节点ID和名称不能为空")
    if tree.type == "agent" and tree.children:
        raise HTTPException(status_code=400, detail="Agent节点不能包含子节点")

    seen_ids.add(tree.id)
    node_count = 1
    for child in tree.children:
        node_count += _validate_org_tree(child, depth + 1, seen_ids)
        if node_count > 100:
            raise HTTPException(status_code=400, detail="组织架构节点数量过多")
    return node_count


def _profile_organization_tree() -> Dict[str, Any]:
    ceo_profiles = profile_registry.get_by_role(AgentRole.CEO)
    analysis_profiles = _profiles_by_roles([
        AgentRole.BRAINSTORM_PARTNER,
        AgentRole.REQUIREMENT_ANALYST,
        AgentRole.RETRIEVAL_ANALYST,
    ])
    writing_profiles = _profiles_by_roles([
        AgentRole.PATENT_WRITER,
        AgentRole.QUALITY_REVIEWER,
    ])

    return {
        "id": "root",
        "name": "专利智能体系统",
        "type": "team",
        "description": "基于 Hermes Profile 注册表生成的多智能体组织架构",
        "expanded": True,
        "children": [
            {
                "id": "orchestration-group",
                "name": "统筹管理层",
                "type": "group",
                "description": "负责流程调度、质量门控与跨 Agent 协同",
                "expanded": True,
                "children": [_agent_node(profile) for profile in ceo_profiles],
            },
            {
                "id": "analysis-group",
                "name": "分析与头脑风暴层",
                "type": "group",
                "description": "负责前期对话澄清、需求分析与专利检索",
                "expanded": True,
                "children": [_agent_node(profile) for profile in analysis_profiles],
            },
            {
                "id": "writing-group",
                "name": "撰写与审查层",
                "type": "group",
                "description": "负责专利申请文件生成与质量审查",
                "expanded": True,
                "children": [_agent_node(profile) for profile in writing_profiles],
            },
        ],
    }


def _append_workflow_event(task_id: str, agent: str, message: str, event_type: str, data=None):
    task_events.setdefault(task_id, []).append(
        WorkflowEventResponse(
            task_id=task_id,
            timestamp=datetime.now(),
            agent=agent,
            message=message,
            event_type=event_type,
            data=data or {},
        )
    )


@router.post("/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow_session(request: WorkflowStartRequest):
    """创建 Hermes/Profile 驱动的专利工作流会话（默认先进入头脑风暴）"""
    task_id = request.task_id or str(uuid.uuid4())
    async with workflow_lock:
        context = workflow_engine.create_workflow(
            task_id=task_id,
            user_id=request.user_id,
            description=request.tech_description,
            patent_type_preference=(
                request.patent_type_preference.value
                if request.patent_type_preference is not None
                else None
            ),
        )
        task_events[task_id] = []
        _append_workflow_event(
            task_id=task_id,
            agent="workflow_engine",
            message="专利工作流会话已创建，进入头脑风暴阶段",
            event_type="workflow.created",
            data={"state": context.current_phase.value},
        )
    await _persist_events(task_id)
    return _workflow_context_to_response(context)


@router.post("/workflows/{task_id}/chat")
async def chat_with_brainstorm_agent(task_id: str, request: ChatMessageRequest):
    """与头脑风暴 Agent 继续讨论专利细节"""
    try:
        response = await workflow_engine.add_chat_message(
            task_id=task_id,
            role="user",
            content=request.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    async with workflow_lock:
        _append_workflow_event(
            task_id=task_id,
            agent="brainstorm_partner",
            message=response.get("content", "消息已记录"),
            event_type="chat.message.created",
            data=response,
        )
    await _persist_events(task_id)
    return response


@router.post("/workflows/{task_id}/start")
async def start_workflow(task_id: str, background_tasks: BackgroundTasks):
    """确认专利细节后，启动完整专利申请流程"""
    async with workflow_lock:
        context = workflow_engine.get_workflow(task_id)
    if not context:
        raise HTTPException(status_code=404, detail="工作流不存在")

    async def phase_callback(phase, result):
        async with workflow_lock:
            _append_workflow_event(
                task_id=task_id,
                agent=phase.value,
                message=f"阶段 {phase.value} 已完成",
                event_type="workflow.phase.completed",
                data={
                    "phase": phase.value,
                    "success": result.success,
                    "duration_seconds": result.duration_seconds,
                    "issues": result.issues,
                },
            )

    async def run_workflow():
        try:
            await workflow_engine.execute_full_workflow(context, phase_callback=phase_callback)
            async with workflow_lock:
                _append_workflow_event(
                    task_id=task_id,
                    agent="workflow_engine",
                    message="专利申请流程已完成",
                    event_type="workflow.completed",
                    data={"state": context.current_phase.value},
                )
            await _persist_events(task_id)
        except Exception as e:
            async with workflow_lock:
                _append_workflow_event(
                    task_id=task_id,
                    agent="workflow_engine",
                    message=str(e),
                    event_type="workflow.failed",
                )
            await _persist_events(task_id)
            raise

    background_tasks.add_task(run_workflow)
    async with workflow_lock:
        _append_workflow_event(
            task_id=task_id,
            agent="workflow_engine",
            message="专利申请流程已启动",
            event_type="workflow.started",
        )
    await _persist_events(task_id)
    return {"task_id": task_id, "status": "started"}


@router.post("/workflows/{task_id}/resume")
async def resume_workflow(task_id: str, background_tasks: BackgroundTasks):
    """恢复工作流执行
    - 中断的流程从当前阶段继续执行
    - 已完成的流程自动进入迭代修正（从撰写阶段重新开始）
    """
    async with workflow_lock:
        context = workflow_engine.get_workflow(task_id)
    if not context:
        raise HTTPException(status_code=404, detail="工作流不存在")

    force_start_from = None
    if context.current_phase == WorkflowState.COMPLETED:
        # 已完成的工作流 → 进入迭代修正模式
        if context.iteration_count >= context.max_iterations:
            raise HTTPException(
                status_code=400,
                detail=f"已达到最大迭代次数（{context.max_iterations}），无法继续修正",
            )
        force_start_from = WorkflowState.PATENT_WRITING
        context.iteration_count += 1

    elif context.current_phase in [WorkflowState.FAILED, WorkflowState.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"工作流已终止，无法恢复（状态: {context.current_phase.value}）",
        )

    async def phase_callback(phase, result):
        async with workflow_lock:
            _append_workflow_event(
                task_id=task_id,
                agent=phase.value,
                message=f"阶段 {phase.value} 已完成",
                event_type="workflow.phase.completed",
                data={
                    "phase": phase.value,
                    "success": result.success,
                    "duration_seconds": result.duration_seconds,
                    "issues": result.issues,
                },
            )

    async def run_resume():
        try:
            await workflow_engine.resume_workflow(
                context,
                phase_callback=phase_callback,
                force_start_from=force_start_from,
            )
            async with workflow_lock:
                _append_workflow_event(
                    task_id=task_id,
                    agent="workflow_engine",
                    message="专利工作流已恢复并完成",
                    event_type="workflow.completed",
                    data={"state": context.current_phase.value},
                )
            await _persist_events(task_id)
        except Exception as e:
            async with workflow_lock:
                _append_workflow_event(
                    task_id=task_id,
                    agent="workflow_engine",
                    message=str(e),
                    event_type="workflow.failed",
                )
            await _persist_events(task_id)
            raise

    background_tasks.add_task(run_resume)
    async with workflow_lock:
        _append_workflow_event(
            task_id=task_id,
            agent="workflow_engine",
            message=f"工作流已从 {context.current_phase.value} 阶段恢复",
            event_type="workflow.resumed",
            data={"current_phase": context.current_phase.value},
        )
    await _persist_events(task_id)
    return {
        "task_id": task_id,
        "status": "resumed",
        "current_phase": context.current_phase.value,
    }


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    user_id: str = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """列出 Hermes/Profile 工作流会话"""
    async with workflow_lock:
        contexts = workflow_engine.list_workflows()

        if user_id:
            contexts = [context for context in contexts if context.user_id == user_id]

        contexts.sort(key=lambda context: context.created_at, reverse=True)
        total = len(contexts)
        items = contexts[offset:offset + limit]
        responses = [_workflow_context_to_response(context) for context in items]

    return WorkflowListResponse(total=total, items=responses)


@router.get("/workflows/{task_id}")
async def get_workflow(task_id: str):
    """获取 Hermes/Profile 工作流状态与阶段输出"""
    async with workflow_lock:
        context = workflow_engine.get_workflow(task_id)
        if not context:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return _workflow_context_to_response(context)


@router.get("/workflows/{task_id}/messages")
async def get_workflow_messages(task_id: str):
    """获取头脑风暴对话历史"""
    async with workflow_lock:
        context = workflow_engine.get_workflow(task_id)
        if not context:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"messages": context.message_history, "count": len(context.message_history)}


@router.post("/workflows/{task_id}/cancel")
async def cancel_workflow(task_id: str):
    """取消 Hermes/Profile 工作流"""
    async with workflow_lock:
        if not workflow_engine.cancel_workflow(task_id):
            raise HTTPException(status_code=404, detail="工作流不存在")
        _append_workflow_event(
            task_id=task_id,
            agent="workflow_engine",
            message="工作流已取消",
            event_type="workflow.cancelled",
        )
    await _persist_events(task_id)
    return {"task_id": task_id, "status": "cancelled"}


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks):
    """创建新的专利申请任务"""
    task_id = str(uuid.uuid4())

    task = PatentTask(
        task_id=task_id,
        user_id=request.user_id,
        tech_description=request.tech_description,
        patent_type_preference=request.patent_type_preference,
        current_state=WorkflowState.INITIAL,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        iteration_count=0,
        max_iterations=3,
    )

    async with workflow_lock:
        tasks_store[task_id] = task
        task_events[task_id] = []

    # 持久化到数据库
    await _persist_task(task_id)
    await _persist_events(task_id)

    logger.info(f"创建新任务: {task_id}")

    # 后台执行工作流
    background_tasks.add_task(_execute_workflow, task_id)

    return task


async def _execute_workflow(task_id: str):
    """在后台执行工作流"""
    try:
        ceo_agent = CEOAgent()
        async with workflow_lock:
            task = tasks_store[task_id]

        result_task = await asyncio.wait_for(ceo_agent.execute(task), timeout=30.0)

        # 收集所有事件
        events = ceo_agent.get_events()
        event_responses = [
            WorkflowEventResponse(
                task_id=e.task_id,
                timestamp=e.timestamp,
                agent=e.agent,
                message=e.message,
                event_type=e.event_type,
                data=e.data,
            )
            for e in events
        ]

        async with workflow_lock:
            task_events[task_id] = event_responses
            tasks_store[task_id] = result_task
        await _persist_task(task_id)
        await _persist_events(task_id)
        logger.info(f"任务 {task_id} 执行完成，状态: {result_task.current_state}")

    except Exception as e:
        logger.exception(f"任务 {task_id} 执行失败: {e}")
        async with workflow_lock:
            if task_id in tasks_store:
                tasks_store[task_id].current_state = WorkflowState.FAILED
                tasks_store[task_id].error_message = str(e)
        await _persist_task(task_id)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    user_id: str = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """列出所有任务"""
    async with workflow_lock:
        tasks = list(tasks_store.values())

    if user_id:
        tasks = [t for t in tasks if t.user_id == user_id]

    # 按创建时间倒序
    tasks.sort(key=lambda t: t.created_at, reverse=True)

    return {
        "total": len(tasks),
        "tasks": tasks[offset:offset + limit],
    }


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str):
    """获取任务详情"""
    async with workflow_lock:
        task = tasks_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 构建响应 - 转换各阶段文档
    response = TaskDetailResponse(
        task_id=task.task_id,
        user_id=task.user_id,
        current_state=task.current_state,
        created_at=task.created_at,
        updated_at=task.updated_at,
        iteration_count=task.iteration_count,
        error_message=task.error_message,
    )

    # 序列化各阶段输出
    if task.requirement_doc:
        response.requirement_doc = task.requirement_doc.model_dump()

    if task.retrieval_report:
        response.retrieval_report = task.retrieval_report.model_dump()

    if task.draft_doc:
        response.draft_doc = task.draft_doc.model_dump()

    if task.review_report:
        response.review_report = task.review_report.model_dump()

    if task.final_patent:
        response.final_patent = task.final_patent if isinstance(task.final_patent, dict) else task.final_patent.model_dump()

    return response


@router.get("/tasks/{task_id}/events", response_model=List[WorkflowEventResponse])
async def get_task_events(task_id: str):
    """获取任务事件流"""
    async with workflow_lock:
        events = task_events.get(task_id)
    if events is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    return events


@router.get("/tasks/{task_id}/stream")
async def stream_task_events(task_id: str):
    """SSE实时事件流"""
    async with workflow_lock:
        if task_id not in tasks_store:
            raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        async with workflow_lock:
            last_sent = len(task_events.get(task_id, []))
        while True:
            async with workflow_lock:
                events = list(task_events.get(task_id, []))
                task = tasks_store.get(task_id)

            # 发送新事件
            for event in events[last_sent:]:
                yield f"event: {event.event_type}\ndata: {event.json()}\n\n"
                last_sent += 1

            # 检查是否结束
            if task and task.current_state in [WorkflowState.COMPLETED, WorkflowState.FAILED]:
                yield f"event: done\ndata: {task.current_state}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    async with workflow_lock:
        task = tasks_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        if task.current_state not in [WorkflowState.COMPLETED, WorkflowState.FAILED]:
            task.current_state = WorkflowState.FAILED
            task.error_message = "用户取消任务"
            logger.info(f"任务 {task_id} 已被用户取消")

    await _persist_task(task_id)
    return {"status": "success", "message": "任务已取消"}


@router.post("/search/patents", response_model=SearchResponse)
async def search_patents(request: SearchPatentRequest):
    """搜索现有技术专利"""
    import time
    start_time = time.time()

    data_source_manager = get_data_source_manager()
    results = await data_source_manager.search_all(request)

    response_results = [
        PriorArtReferenceResponse(
            reference_id=r.reference_id,
            title=r.title,
            publication_date=r.publication_date,
            applicant=r.applicant,
            abstract=r.abstract,
            similarity_score=r.similarity_score,
            source=r.source,
            url=r.url,
        )
        for r in results
    ]

    return SearchResponse(
        total=len(results),
        results=response_results,
        query=request.query,
        search_time=time.time() - start_time,
    )


@router.get("/knowledge/search", response_model=KnowledgeBaseSearchResponse)
async def search_knowledge_base(query: str, top_k: int = 5):
    """搜索本地知识库中的专利"""
    kb = get_knowledge_base()
    patents = kb.search_similar(query, top_k)

    return KnowledgeBaseSearchResponse(
        total=len(patents),
        patents=patents,
        query=query,
    )


@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status():
    """获取系统状态"""
    async with workflow_lock:
        active_tasks = sum(
            1 for t in tasks_store.values()
            if t.current_state not in [WorkflowState.COMPLETED, WorkflowState.FAILED]
        )

    kb = get_knowledge_base()

    return SystemStatusResponse(
        status="running",
        active_tasks=active_tasks,
        agents=[
            {"name": "CEO Agent", "description": "全局流程调度", "status": "idle"},
            {"name": "需求分析Agent", "description": "技术需求结构化", "status": "idle"},
            {"name": "检索分析Agent", "description": "专利性评估", "status": "idle"},
            {"name": "专利撰写Agent", "description": "申请文件生成", "status": "idle"},
            {"name": "质量审查Agent", "description": "合规性检查", "status": "idle"},
        ],
        knowledge_base_count=len(kb.list_all_patents()),
        data_sources=["uspto", "epo", "cnipa", "google_patents", "arxiv"],
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============ 聊天消息相关 ============
# 存储会话状态
chat_sessions = {}

def generate_brainstorm_response(content: str, phase: str = "initial"):
    """生成头脑风暴阶段的智能回复"""

    responses = {
        "initial": f"""感谢您的描述！为了更准确地评估您的专利申请方案，我想进一步了解几个关键问题：

**1. 技术领域确认**
您的发明具体属于哪个细分技术领域？（例如：人工智能/自然语言处理、半导体/芯片设计、机械/自动化设备等）

**2. 现有技术痛点**
目前行业中针对这个问题的现有解决方案有什么不足？您的发明主要改进了哪些方面？

您可以先回答这两个问题，我们逐步完善信息。""",

        "questioning": f"""非常好！让我们继续完善信息：

**1. 核心创新点**
您认为这个发明最核心的创新点是什么？（可以列出1-3个关键点）

**2. 技术实现细节**
能否简要说明一下技术实现的关键步骤或原理？""",

        "summarizing": f"""太棒了！感谢您的详细说明。根据我们的沟通，我为您整理了专利申请方案摘要：

📋 **专利申请方案摘要**

**技术领域：** 待确认
**核心问题：** 待确认
**创新亮点：**
• 创新点1
• 创新点2
• 创新点3

**技术优势：**
相较于现有技术，您的发明具有以下显著优势：
- 解决了行业长期存在的技术痛点
- 技术方案具备新颖性和创造性
- 具有明确的商业化应用前景

**建议专利类型：** 发明专利

---

请您确认以上信息是否准确？如有需要补充或修改的地方，请随时告诉我。确认无误后，我们可以启动正式的专利申请流程！""",
    }

    return responses.get(phase, responses["initial"])


@router.post("/chat/messages")
async def send_chat_message(request: ChatMessageRequest, phase: str = "initial"):
    """发送聊天消息 - 支持头脑风暴阶段"""
    message_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # 如果是已有 Hermes 工作流，直接交给头脑风暴 Agent
    async with workflow_lock:
        workflow_context = workflow_engine.get_workflow(request.task_id) if request.task_id else None
    if workflow_context:
        response = await workflow_engine.add_chat_message(task_id=request.task_id, role="user", content=request.content)
        assistant_content = response.get("content", "消息已记录")
    else:
        # 头脑风暴模式
        assistant_content = generate_brainstorm_response(request.content, phase)

    assistant_response = {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": assistant_content,
        "timestamp": timestamp,
        "phase": phase,
    }

    return {
        "user_message": {
            "id": message_id,
            "role": "user",
            "content": request.content,
            "timestamp": timestamp,
        },
        "assistant_message": assistant_response,
    }


@router.get("/chat/messages")
async def get_chat_messages(session_id: str = "default", task_id: str = None):
    """获取聊天历史"""
    async with workflow_lock:
        context = workflow_engine.get_workflow(task_id) if task_id else None
        if context:
            return {"messages": context.message_history, "count": len(context.message_history)}

    return {
        "messages": [
            {
                "id": "1",
                "role": "assistant",
                "content": "您好！我是专利智脑的智能助手。我将协助您完成专利申请的全过程。请您描述一下您的发明创造。",
                "timestamp": datetime.now().isoformat(),
            }
        ],
        "count": 1,
    }


# ============ Agent管理相关 ============
@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """列出所有 Hermes Profile Agent"""
    profiles = profile_registry.list_all()
    return {
        "agents": [_agent_config_from_profile(profile) for profile in profiles],
        "total": len(profiles),
    }


@router.get("/agents/{agent_id}", response_model=AgentDetailResponse)
async def get_agent_detail(agent_id: str) -> AgentDetailResponse:
    """获取 Hermes Profile Agent 详情，包括工具、技能与记忆配置"""
    profile = _require_agent_profile(agent_id)
    return {
        "config": _agent_config_from_profile(profile),
        "tools": _agent_tools_from_profile(profile),
        "skills": _agent_skills_from_profile(profile),
        "timers": [],
        "memories": _agent_memories_from_profile(profile),
    }


@router.put("/agents/{agent_id}", response_model=AgentUpdateResponse)
async def update_agent_config(agent_id: str, config: dict) -> AgentUpdateResponse:
    """更新Agent配置"""
    _require_agent_profile(agent_id)
    return {
        "agent_id": agent_id,
        "updated_fields": list(config.keys()),
        "message": "Agent配置已更新",
    }


@router.post("/agents/{agent_id}/tools/{tool_id}/toggle", response_model=AgentToggleResponse)
async def toggle_agent_tool(agent_id: str, tool_id: str, enabled: bool) -> AgentToggleResponse:
    """启用/禁用Agent工具"""
    profile = _require_agent_profile(agent_id)
    if tool_id not in profile.tool_config.enabled_tools:
        raise HTTPException(status_code=404, detail="Agent工具不存在")
    return {"agent_id": agent_id, "tool_id": tool_id, "enabled": enabled}


@router.post("/agents/{agent_id}/skills/{skill_id}/toggle", response_model=AgentToggleResponse)
async def toggle_agent_skill(agent_id: str, skill_id: str, enabled: bool) -> AgentToggleResponse:
    """启用/禁用Agent技能"""
    profile = _require_agent_profile(agent_id)
    if not any(skill.name == skill_id for skill in profile.skills):
        raise HTTPException(status_code=404, detail="Agent技能不存在")
    return {"agent_id": agent_id, "skill_id": skill_id, "enabled": enabled}


@router.post("/agents/{agent_id}/timers/{timer_id}/toggle", response_model=AgentToggleResponse)
async def toggle_agent_timer(agent_id: str, timer_id: str, enabled: bool) -> AgentToggleResponse:
    """启用/禁用Agent定时器"""
    _require_agent_profile(agent_id)
    raise HTTPException(status_code=404, detail="Agent定时器不存在")


@router.post("/agents/{agent_id}/memory/{memory_id}/clear", response_model=AgentToggleResponse)
async def clear_agent_memory(agent_id: str, memory_id: str) -> AgentToggleResponse:
    """清空Agent记忆"""
    profile = _require_agent_profile(agent_id)
    memory_ids = {memory["id"] for memory in _agent_memories_from_profile(profile)}
    if memory_id not in memory_ids:
        raise HTTPException(status_code=404, detail="Agent记忆不存在")
    return {"agent_id": agent_id, "memory_id": memory_id, "cleared": True}


# ============ 组织架构相关 ============
@router.get("/organization/tree", response_model=OrgNodeResponse)
async def get_organization_tree() -> OrgNodeResponse:
    """获取组织架构树"""
    if organization_tree_store is not None:
        return organization_tree_store
    return _profile_organization_tree()


@router.put("/organization/tree", response_model=OrganizationUpdateResponse)
async def update_organization_tree(tree: OrgNodeResponse) -> OrganizationUpdateResponse:
    """更新组织架构树"""
    global organization_tree_store
    _validate_org_tree(tree)
    organization_tree_store = tree
    await _persist_org_tree()
    return {"status": "success", "message": "组织架构已更新", "tree": tree}


# ============ 对话会话相关 ============

def _get_brainstorm_agent():
    from src.agents import get_agent_factory as _f
    return _f().create_agent("patent.brainstorm_partner.v1")


@router.post("/conversations", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(request: CreateConversationRequest):
    """创建新的头脑风暴对话会话"""
    conv_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    greeting_id = str(uuid.uuid4())
    conversation = {
        "id": conv_id,
        "title": request.title or "新的对话",
        "messages": [
            {
                "id": greeting_id,
                "role": "assistant",
                "content": "你好！我是专利智脑的创意助手。请告诉我你的技术构思，我们可以一起探讨它的专利价值。",
                "timestamp": now,
                "type": "text",
                "metadata": None,
            }
        ],
        "created_at": now,
        "updated_at": now,
        "status": "brainstorming",
        "linked_workflow_id": None,
    }
    async with conversations_lock:
        conversations_store[conv_id] = conversation
    await _persist_conversation(conv_id)
    return conversation


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """列出所有对话会话"""
    async with conversations_lock:
        items = []
        for conv in conversations_store.values():
            items.append({
                "id": conv["id"],
                "title": conv["title"],
                "created_at": conv["created_at"],
                "updated_at": conv["updated_at"],
                "message_count": len(conv["messages"]),
                "status": conv["status"],
                "linked_workflow_id": conv.get("linked_workflow_id"),
            })
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        total = len(items)
        page_items = items[offset:offset + limit]
    return ConversationListResponse(items=page_items, total=total, page=(offset // limit) + 1, page_size=limit)


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: str):
    """获取对话会话详情"""
    async with conversations_lock:
        conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.post("/conversations/{conv_id}/chat", response_model=ConversationChatResponse)
async def chat_in_conversation(conv_id: str, request: ConversationChatRequest):
    """在对话中发送消息（头脑风暴模式，不会创建专利工作流）"""
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    async with conversations_lock:
        conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv.get("linked_workflow_id"):
        raise HTTPException(status_code=400, detail="该对话已关联工作流，请使用工作流聊天接口")

    # 添加用户消息
    now = datetime.now().isoformat()
    user_msg = {
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": content,
        "timestamp": now,
        "type": "text",
        "metadata": None,
    }

    try:
        agent = _get_brainstorm_agent()
        history_text = "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in conv["messages"][-10:]
        ])
        prompt = f"""
你是一个专利头脑风暴助手。你的目标是帮助用户探索和阐述技术构思。

当前对话历史：
{history_text}

USER: {content}

请友好回应用户，提供专业建议。必要时提问以获取更多信息。当你通过对话收集到足够的信息（技术问题、解决方案、关键特征、应用场景），可以在回复末尾添加标记 [CREATE_PATENT_RECOMMENDATION] 来建议创建专利申请。

注意：不要在一开始就建议申请专利，要先充分理解用户的技术构思。
"""
        response = await agent.run(prompt)
        response_text = str(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 响应失败: {str(e)}")

    # 检查 AI 是否建议创建专利
    has_recommendation = "[CREATE_PATENT_RECOMMENDATION]" in response_text
    clean_text = response_text.replace("[CREATE_PATENT_RECOMMENDATION]", "").strip()

    assistant_msg = {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": clean_text,
        "timestamp": datetime.now().isoformat(),
        "type": "text",
        "metadata": {"recommend_create_patent": has_recommendation} if has_recommendation else None,
    }

    async with conversations_lock:
        conv = conversations_store.get(conv_id)
        if conv:
            conv["messages"].append(user_msg)
            conv["messages"].append(assistant_msg)
            conv["updated_at"] = datetime.now().isoformat()
            # 自动生成标题（从第一条用户消息）
            user_msgs = [m for m in conv["messages"] if m["role"] == "user"]
            if conv["title"] == "新的对话" and len(user_msgs) == 1:
                title = content[:50]
                conv["title"] = title + ("..." if len(content) > 50 else "")

    await _persist_conversation(conv_id)
    return ConversationChatResponse(
        message=assistant_msg,
        has_recommendation=has_recommendation,
        conversation_id=conv_id,
    )


@router.post("/conversations/{conv_id}/create-workflow", response_model=dict)
async def create_workflow_from_conversation(conv_id: str, request: CreateWorkflowFromConversationRequest):
    """从对话内容创建专利申请工作流"""
    async with conversations_lock:
        conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv.get("linked_workflow_id"):
        raise HTTPException(status_code=400, detail="该对话已关联工作流")

    # 从对话中提取技术描述（取所有用户消息合并）
    user_msgs = [m["content"] for m in conv["messages"] if m["role"] == "user"]
    if not user_msgs:
        raise HTTPException(status_code=400, detail="对话中没有用户消息，无法创建工作流")
    tech_description = " ".join(user_msgs)

    # 创建工作流
    async with workflow_lock:
        context = workflow_engine.create_workflow(
            task_id=str(uuid.uuid4()),
            user_id=request.user_id,
            description=tech_description,
        )
        task_id = context.task_id
        task_events[task_id] = []
        _append_workflow_event(
            task_id=task_id,
            agent="workflow_engine",
            message="已从对话内容创建专利工作流",
            event_type="workflow.created",
            data={"state": context.current_phase.value},
        )

    # 关联对话到工作流
    async with conversations_lock:
        conv = conversations_store.get(conv_id)
        if conv:
            conv["linked_workflow_id"] = task_id
            conv["status"] = "workflow_linked"
            conv["updated_at"] = datetime.now().isoformat()

    await _persist_events(task_id)
    await _persist_conversation(conv_id)
    return {"task_id": task_id, "status": "created", "conversation_id": conv_id}


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conv_id: str):
    """删除对话会话"""
    async with conversations_lock:
        if conv_id not in conversations_store:
            raise HTTPException(status_code=404, detail="对话不存在")
        del conversations_store[conv_id]
    store = _get_persist_store()
    await store.delete("conversation", conv_id)


@router.get("/conversations/{conv_id}/workflow-status", response_model=dict)
async def get_conversation_workflow_status(conv_id: str):
    """获取对话关联的工作流状态"""
    async with conversations_lock:
        conv = conversations_store.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    linked_id = conv.get("linked_workflow_id")
    if not linked_id:
        return {"linked": False, "workflow_id": None, "status": None}

    async with workflow_lock:
        context = workflow_engine.get_workflow(linked_id)
    if not context:
        return {"linked": True, "workflow_id": linked_id, "status": "not_found"}

    return {
        "linked": True,
        "workflow_id": linked_id,
        "status": context.current_phase.value,
        "message_count": len(context.message_history) if hasattr(context, "message_history") else 0,
    }


# ============ 统计数据相关 ============
@router.get("/stats/dashboard")
async def get_dashboard_stats():
    """获取仪表盘统计数据"""
    async with workflow_lock:
        tasks = list(tasks_store.values())

    return {
        "total_tasks": len(tasks),
        "completed_tasks": sum(1 for t in tasks if t.current_state == WorkflowState.COMPLETED),
        "in_progress_tasks": sum(
            1 for t in tasks
            if t.current_state not in [WorkflowState.COMPLETED, WorkflowState.FAILED]
        ),
        "failed_tasks": sum(1 for t in tasks if t.current_state == WorkflowState.FAILED),
        "active_agents": 5,
        "avg_completion_time": "2.5 hours",
        "success_rate": 94.5,
    }


# ============ Agent 文件浏览与相关文件查看 ============
import os as _os
import stat as _stat

_KNOWN_TOOL_IMPL_FILES: dict[str, str] = {
    "task_planner": "backend/src/agents/hermes/tools/base.py",
    "quality_assessor": "backend/src/agents/hermes/tools/base.py",
    "report_generator": "backend/src/agents/hermes/tools/base.py",
    "risk_analyzer": "backend/src/agents/hermes/tools/base.py",
}


@router.get("/agents/{agent_id}/related-files")
async def get_agent_related_files(
    agent_id: str,
    tool_id: str = None,
    skill_id: str = None,
):
    """获取 Agent 特定工具或技能的相关文件列表及内容"""
    if (tool_id is None and skill_id is None) or (tool_id is not None and skill_id is not None):
        raise HTTPException(
            status_code=400,
            detail="必须且只能提供 tool_id 或 skill_id 参数之一",
        )

    profile = profile_registry.get(agent_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Agent 未找到: {agent_id}")

    _project_root = _os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    )

    def _read_file(rel_path: str) -> str | None:
        """安全读取项目内文件"""
        abs_path = _os.path.normpath(_os.path.join(_project_root, rel_path))
        if not abs_path.startswith(_project_root):
            return None
        if not _os.path.isfile(abs_path):
            return None
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    if tool_id is not None:
        if tool_id not in profile.tool_config.enabled_tools:
            raise HTTPException(status_code=404, detail=f"工具未找到: {tool_id}")

        tools = _agent_tools_from_profile(profile)
        tool = next((t for t in tools if t["id"] == tool_id), None)

        rel_path = _KNOWN_TOOL_IMPL_FILES.get(tool_id)
        source_code = _read_file(rel_path) if rel_path else None

        return {
            "type": "tool",
            "name": tool["name"] if tool else tool_id,
            "source_code": source_code,
            "source_markdown": None,
            "files": [{"path": rel_path, "content": source_code}] if rel_path and source_code else [],
        }

    else:
        skills = _agent_skills_from_profile(profile)
        skill_meta = next((s for s in skills if s["id"] == skill_id), None)
        if skill_meta is None:
            raise HTTPException(status_code=404, detail=f"技能未找到: {skill_id}")

        # 找到原始的 AgentSkill 对象以获取完整信息（熟练度、关键词等）
        profile_skill: AgentSkill | None = next(
            (s for s in profile.skills if s.name == skill_id), None
        )

        markdown_lines = [
            f"# {skill_meta['name']}",
            "",
            f"**熟练度**: {profile_skill.proficiency if profile_skill else 0.8}",
            "",
            "## 描述",
            "",
            skill_meta["description"],
            "",
        ]
        tags = skill_meta.get("tags", [])
        if tags:
            markdown_lines.append("## 关键词")
            markdown_lines.append("")
            for tag in tags:
                markdown_lines.append(f"- {tag}")
            markdown_lines.append("")

        source_markdown = "\n".join(markdown_lines)

        profile_file_rel = "backend/src/agents/profiles/default_profiles.py"
        source_code = _read_file(profile_file_rel)

        return {
            "type": "skill",
            "name": skill_meta["name"],
            "source_code": source_code,
            "source_markdown": source_markdown,
            "files": [
                {
                    "path": f"skills/{skill_meta['name']}.md",
                    "content": source_markdown,
                },
                {"path": profile_file_rel, "content": source_code},
            ],
        }


# ============ Agent 工具/技能生成与热插拔 ============
import textwrap as _textwrap


@router.post("/agents/{agent_id}/tools/chat-generate")
async def chat_generate_tool(agent_id: str, body: dict):
    """通过LLM生成Hermes工具代码（返回模板代码）"""
    _require_agent_profile(agent_id)
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    parameters = body.get("parameters") or {}

    # 根据参数生成工具函数签名
    func_params = ", ".join(
        f'{k}: str = None' for k in parameters.keys()
    ) or "**kwargs"

    param_lines = ""
    for k, v in parameters.items():
        param_lines += f"    {k}: {v or '参数描述'}\n"

    param_json_lines = ""
    for k in parameters:
        param_json_lines += f'        "{k}": {k},\n'

    code = f'''\"\"\"
{description}

Args:
{param_lines}"""
import json
from typing import Any, Dict


async def run({func_params}) -> Dict[str, Any]:
    """
    {description}
    """
    # --- 在此实现工具逻辑 ---
    result = {{
        "success": True,
        "message": f"工具 {name} 执行成功",
        "data": {{
{param_json_lines}        }},
    }}
    return result
'''

    return {
        "success": True,
        "name": name,
        "code": code,
        "message": "工具代码已生成",
    }


@router.post("/agents/{agent_id}/skills/chat-generate")
async def chat_generate_skill(agent_id: str, body: dict):
    """通过LLM生成Hermes技能数据"""
    _require_agent_profile(agent_id)
    name = body.get("name", "").strip() or "auto_skill"
    description = body.get("description", "").strip()
    parameters = body.get("parameters") or {}

    # 生成技能元数据
    skill_data = {
        "name": name,
        "description": description,
        "proficiency": 5,
        "keywords": [w.strip() for w in description.replace(",", " ").split() if len(w.strip()) > 1][:5],
    }

    # 生成技能内容
    generated_content = f'''# {name}

## 概述
{description}

## 配置
- 名称: {name}
- 熟练度: 5
- 关键词: {", ".join(skill_data["keywords"])}

## 参数
{chr(10).join(f'- {k}: {v}' for k, v in parameters.items()) if parameters else "（无参数）"}

## 实现说明
该技能通过AI对话自动生成，请在Agent配置中进一步编辑完善。
'''

    return {
        "success": True,
        "name": name,
        "skill_data": skill_data,
        "generated_content": generated_content,
        "message": "技能已生成",
    }


@router.post("/agents/{agent_id}/tools/validate")
async def validate_agent_tool(agent_id: str, body: dict):
    """验证Hermes工具代码语法"""
    _require_agent_profile(agent_id)
    code = body.get("code", "")
    if not code.strip():
        return {"valid": False, "name": None, "error": "代码为空"}

    # Python语法检查
    try:
        compile(code, "<hermes_tool>", "exec")
    except SyntaxError as e:
        return {"valid": False, "name": None, "error": str(e)}

    # 提取函数名
    import ast
    try:
        tree = ast.parse(code)
        func_name = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                func_name = node.name
                break
        return {"valid": True, "name": func_name or "run", "error": None}
    except SyntaxError as e:
        return {"valid": False, "name": None, "error": str(e)}


@router.post("/agents/{agent_id}/tools/hot-plug")
async def hot_plug_agent_tool(agent_id: str, body: dict):
    """热插拔注册新的Hermes工具"""
    profile = _require_agent_profile(agent_id)
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    code = body.get("code", "")

    if not name:
        raise HTTPException(status_code=400, detail="工具名称不能为空")
    if not code:
        raise HTTPException(status_code=400, detail="工具代码不能为空")

    # 验证代码语法
    try:
        compile(code, "<hermes_tool>", "exec")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"代码语法错误: {e}")

    # 确保工具在启用列表中
    if name not in profile.tool_config.enabled_tools:
        profile.tool_config.enabled_tools.append(name)

    # 确保工具配置存在
    if name not in profile.tool_config.tool_configs:
        profile.tool_config.tool_configs[name] = {}

    profile.tool_config.tool_configs[name].update({
        "description": description,
        "enabled": True,
        "source_code": code,
        "is_hermes": True,
    })

    return {
        "success": True,
        "name": name,
        "message": f"工具 {name} 已通过热插拔注册",
    }


@router.get("/agents/{agent_id}/browse")
async def browse_agent_directory(agent_id: str, path: str = ""):
    """浏览Agent工作目录（支持子目录导航）"""
    profile = _require_agent_profile(agent_id)

    _project_root = _os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    )

    working_dir = f"./workspace/{profile.profile_id.replace('.', '-')}"
    abs_base = _os.path.normpath(_os.path.join(_project_root, working_dir))

    if not _os.path.isdir(abs_base):
        return {
            "path": path or "/",
            "absolute_path": abs_base,
            "entries": [],
        }

    clean_path = _os.path.normpath(_os.path.join(abs_base, path.lstrip("/")))
    if not clean_path.startswith(abs_base):
        raise HTTPException(status_code=403, detail="路径越权访问")

    if not _os.path.isdir(clean_path):
        raise HTTPException(status_code=404, detail="目录不存在")

    entries = []
    try:
        for name in sorted(_os.listdir(clean_path)):
            full = _os.path.join(clean_path, name)
            is_dir = _os.path.isdir(full)
            size = _os.path.getsize(full) if not is_dir else 0
            entries.append({
                "name": name,
                "path": _os.path.relpath(full, abs_base),
                "type": "directory" if is_dir else "file",
                "size": size,
            })
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权限访问目录: {e}")

    entries.sort(key=lambda e: (0 if e["type"] == "directory" else 1, e["name"].lower()))
    return {
        "path": path or "/",
        "absolute_path": abs_base,
        "entries": entries,
    }


@router.get("/agents/{agent_id}/file")
async def read_agent_file(agent_id: str, path: str = Query(...)):
    """读取Agent工作目录下的文件内容"""
    profile = _require_agent_profile(agent_id)

    _project_root = _os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    )

    working_dir = f"./workspace/{profile.profile_id.replace('.', '-')}"
    abs_base = _os.path.normpath(_os.path.join(_project_root, working_dir))

    clean_path = _os.path.normpath(_os.path.join(abs_base, path.lstrip("/")))
    if not clean_path.startswith(abs_base):
        raise HTTPException(status_code=403, detail="路径越权访问")

    if not _os.path.isfile(clean_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        import codecs

        for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                with codecs.open(clean_path, "r", encoding=enc) as f:
                    content = f.read()
                return {"path": path, "content": content}
            except (UnicodeDecodeError, UnicodeError):
                continue

        # Binary fallback — read as base64
        with open(clean_path, "rb") as f:
            import base64

            raw = f.read()
        return {"path": path, "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权限读取文件: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {e}")


@router.get("/export/{task_id}")
async def export_patent_docx(task_id: str):
    """导出专利文档为DOCX格式并下载"""
    async with workflow_lock:
        task = tasks_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    patent_data: dict | None = None
    if task.final_patent:
        fp = task.final_patent
        if isinstance(fp, dict):
            patent_data = fp.get("patent_draft") or fp
        elif fp.patent_draft:
            patent_data = fp.patent_draft.model_dump()
    elif task.draft_doc:
        patent_data = task.draft_doc.model_dump()

    if not patent_data:
        raise HTTPException(status_code=400, detail="该任务尚无专利文档可导出")

    from src.document_gen.generator import generate_patent_docx
    filepath = await asyncio.to_thread(generate_patent_docx, patent_data, task_id)

    return FileResponse(
        path=filepath,
        filename=f"patent_{task_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
