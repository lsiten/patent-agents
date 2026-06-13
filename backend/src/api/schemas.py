from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

from ..models.enums import WorkflowState, PatentType, Severity


# ==================== 请求模型 ====================

class CreateTaskRequest(BaseModel):
    """创建专利申请任务请求"""
    tech_description: str = Field(..., min_length=50, description="技术发明描述")
    patent_type_preference: Optional[PatentType] = Field(None, description="偏好的专利类型")
    target_country: str = Field("中国", description="目标申请国家/法域（默认中国，可指定美国、欧洲等）")
    user_id: str = Field(..., description="用户ID")
    title: Optional[str] = Field(None, description="发明标题")
    reference_urls: List[str] = Field(default_factory=list, description="参考资料URL")


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    task_id: str
    user_feedback: Optional[str] = None
    supplementary_info: Optional[Dict[str, Any]] = None


class ChatMessageRequest(BaseModel):
    """头脑风暴聊天消息请求"""
    content: str = Field(..., min_length=1, description="用户消息内容")
    user_id: str = Field(default="default_user", description="用户ID")
    task_id: Optional[str] = Field(None, description="已有工作流任务ID")


class WorkflowStartRequest(BaseModel):
    """启动专利申请工作流请求"""
    tech_description: str = Field(..., min_length=20, description="技术发明描述")
    user_id: str = Field(default="default_user", description="用户ID")
    patent_type_preference: Optional[PatentType] = Field(None, description="偏好的专利类型")
    target_country: str = Field("中国", description="目标申请国家/法域（默认中国，可指定美国、欧洲等）")
    task_id: Optional[str] = Field(None, description="可选：已有头脑风暴任务ID")


class SearchPatentRequest(BaseModel):
    """专利检索请求"""
    query: str
    tech_field: Optional[str] = None
    max_results: int = 20
    databases: List[str] = Field(default_factory=list)


class WorkflowDecisionRequest(BaseModel):
    """工作流补救决策请求"""
    action: Literal["continue_auto_fix", "provide_info"]
    supplemental_info: Optional[str] = None


# ==================== 响应模型 ====================

class TaskResponse(BaseModel):
    """任务基本信息响应"""
    task_id: str
    user_id: str
    title: Optional[str] = None
    current_state: WorkflowState
    created_at: datetime
    updated_at: datetime
    iteration_count: int
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaskDetailResponse(TaskResponse):
    """任务详情响应"""
    # 各阶段输出（根据进度返回对应数据
    requirement_doc: Optional[Dict[str, Any]] = None
    retrieval_report: Optional[Dict[str, Any]] = None
    draft_doc: Optional[Dict[str, Any]] = None
    review_report: Optional[Dict[str, Any]] = None
    final_patent: Optional[Dict[str, Any]] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[TaskResponse]


class WorkflowPhaseResultResponse(BaseModel):
    """Hermes/Profile 工作流阶段结果响应"""
    phase: str
    success: bool
    duration_seconds: float
    output: Dict[str, Any] = Field(default_factory=dict)
    issues: List[str]
    warnings: List[str]


class WorkflowResponse(BaseModel):
    """Hermes/Profile 工作流响应"""
    task_id: str
    user_id: str
    title: str = "未命名专利"
    current_state: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    iteration_count: int
    message_count: int
    phase_history: List[WorkflowPhaseResultResponse]
    outputs: Dict[str, Dict[str, Any]]
    target_country: str = "中国"
    quality_remediation: Optional[Dict[str, Any]] = None


class WorkflowListResponse(BaseModel):
    """Hermes/Profile 工作流列表响应"""
    total: int
    items: List[WorkflowResponse]


class WorkflowEventResponse(BaseModel):
    """工作流事件响应"""
    task_id: str
    timestamp: datetime
    agent: str
    message: str
    event_type: str
    data: Optional[Dict[str, Any]] = None


class PriorArtReferenceResponse(BaseModel):
    """现有技术参考响应"""
    reference_id: str
    title: str
    publication_date: Optional[str] = None
    applicant: Optional[str] = None
    abstract: str = ""
    similarity_score: float = 0.0
    source: str = ""
    url: Optional[str] = None


class SearchResponse(BaseModel):
    """检索响应"""
    total: int
    results: List[PriorArtReferenceResponse]
    query: str
    search_time: float


class DownloadResponse(BaseModel):
    """下载响应"""
    task_id: str
    file_type: str
    download_url: str
    file_size: int
    generated_at: datetime


class AgentStatusResponse(BaseModel):
    """Agent状态响应"""
    name: str
    description: str
    status: str
    current_task: Optional[str] = None


class AgentConfigResponse(BaseModel):
    """Agent 配置响应"""
    id: str
    name: str
    description: str
    role: Literal["orchestrator", "specialist", "assistant", "critic"]
    system_prompt: str
    model: str
    temperature: float
    max_tokens: int
    working_directory: str
    enabled: bool
    created_at: str
    updated_at: str
    parent_id: Optional[str] = None
    child_ids: List[str]


class AgentToolResponse(BaseModel):
    """Agent 工具响应"""
    id: str
    name: str
    description: str
    enabled: bool
    category: Literal["search", "file", "analysis", "external"]
    config: Dict[str, str] = Field(default_factory=dict)
    source_code: Optional[str] = None
    is_hermes: Optional[bool] = None
    related_files: List[str] = Field(default_factory=list)


class AgentSkillResponse(BaseModel):
    """Agent 技能响应"""
    id: str
    name: str
    description: str
    enabled: bool
    version: str
    tags: List[str]
    source_code: Optional[str] = None
    source_markdown: Optional[str] = None
    related_files: List[str] = Field(default_factory=list)


class AgentTimerResponse(BaseModel):
    """Agent 定时器响应"""
    id: str
    name: str
    enabled: bool
    cron_expression: str
    action: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None


class MemoryEntryResponse(BaseModel):
    """记忆条目响应"""
    id: str
    type: Literal["fact", "context", "preference", "knowledge", "event"]
    key: str
    value: str
    score: Optional[float] = None
    created_at: str
    updated_at: str
    tags: Optional[List[str]] = None


class AgentMemoryResponse(BaseModel):
    """Agent 记忆响应"""
    id: str
    type: Literal["short_term", "long_term", "knowledge_base"]
    name: str
    size: int
    item_count: int
    last_updated: str
    content: Optional[str] = None
    entries: Optional[List[MemoryEntryResponse]] = None


class AgentListResponse(BaseModel):
    """Agent 列表响应"""
    agents: List[AgentConfigResponse]
    total: int


class ResolvedLLMConfigResponse(BaseModel):
    """Agent 最终生效的 LLM 配置（用于前端展示）"""
    provider: str
    base_url: str
    api_key_masked: str
    model: str
    is_default: bool
    source: str  # "global" | "agent_yaml" | "runtime_override"


class ResolvedImageGenConfigResponse(BaseModel):
    """Agent 最终生效的生图配置"""
    provider: str
    base_url: str
    api_key_masked: str
    model_id: str
    is_default: bool
    source: str


class AgentDetailResponse(BaseModel):
    """Agent 详情响应"""
    config: AgentConfigResponse
    tools: List[AgentToolResponse]
    skills: List[AgentSkillResponse]
    timers: List[AgentTimerResponse]
    memories: List[AgentMemoryResponse]
    llm_config: Optional[ResolvedLLMConfigResponse] = None
    image_gen_config: Optional[ResolvedImageGenConfigResponse] = None


class AgentLLMConfigUpdateRequest(BaseModel):
    """更新 agent LLM 配置请求"""
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # 明文；后端会加密存储
    model: Optional[str] = None
    use_default: bool = False  # True 时清除 runtime override


class AgentImageGenConfigUpdateRequest(BaseModel):
    """更新 agent 生图配置请求"""
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: Optional[str] = None
    use_default: bool = False


class AgentModelConfigTestResponse(BaseModel):
    """测试连通性响应"""
    success: bool
    latency_ms: float = 0.0
    error: Optional[str] = None


class AgentUpdateResponse(BaseModel):
    """Agent 更新响应"""
    agent_id: str
    updated_fields: List[str]
    message: str


class CreateTimerRequest(BaseModel):
    """创建定时器请求"""
    name: str = "未命名定时器"
    enabled: bool = True
    cron_expression: str = "0 0 * * *"
    action: str = ""


class AgentToggleResponse(BaseModel):
    """Agent 开关响应"""
    agent_id: str
    enabled: Optional[bool] = None
    tool_id: Optional[str] = None
    skill_id: Optional[str] = None
    timer_id: Optional[str] = None
    memory_id: Optional[str] = None
    cleared: Optional[bool] = None


class OrgNodeResponse(BaseModel):
    """组织架构节点响应"""
    id: str
    name: str
    type: Literal["team", "group", "agent"]
    description: Optional[str] = None
    children: List["OrgNodeResponse"] = Field(default_factory=list)
    expanded: Optional[bool] = None
    agent_config: Optional[AgentConfigResponse] = None


class OrganizationUpdateResponse(BaseModel):
    """组织架构更新响应"""
    status: str
    message: str
    tree: OrgNodeResponse


OrgNodeResponse.model_rebuild()


# ==================== 知识库响应 ====================

class FinalizedPatentResponse(BaseModel):
    """已定稿专利响应"""
    patent_id: str
    title: str
    tech_field: str
    quality_score: Optional[float] = None
    is_exemplar: bool = False
    created_at: datetime


class KnowledgeBaseSearchResponse(BaseModel):
    """知识库搜索响应"""
    total: int
    patents: List[FinalizedPatentResponse]
    query: str


# ==================== 对话系统 ====================

class ConversationSummary(BaseModel):
    """对话会话摘要"""
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    status: str
    linked_workflow_id: Optional[str] = None
    workflow_state: Optional[str] = None
    active_reply: Optional[Dict[str, Any]] = None


class ToolCallInfo(BaseModel):
    """工具/技能调用信息"""
    name: str
    parameters: Dict[str, Any] = {}
    result: Optional[Any] = None
    success: bool = True
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class AgentEventInfo(BaseModel):
    """Agent事件记录（用于持久化和回放）"""
    id: str
    sequence: int
    call_id: str
    type: str  # thinking | tool_call_start | tool_call_end | skill_use | status | dispatch
    agent_name: str
    timestamp: str
    message: str = ""
    data: Dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def fill_legacy_identity_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        timestamp = str(data.get("timestamp") or "")
        event_type = str(data.get("type") or "agent_event")
        data.setdefault("id", f"legacy-{event_type}-{timestamp}")
        data.setdefault("sequence", 0)
        data.setdefault("call_id", "legacy")
        return data


class ConversationMessage(BaseModel):
    """对话消息"""
    id: str
    role: str
    content: str
    timestamp: str
    type: str = "text"
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[ToolCallInfo]] = None
    agent_events: Optional[List[AgentEventInfo]] = None


class ConversationDetail(BaseModel):
    """对话会话详情"""
    id: str
    title: str
    messages: List[ConversationMessage]
    created_at: str
    updated_at: str
    status: str
    linked_workflow_id: Optional[str] = None
    workflow_state: Optional[str] = None
    active_reply: Optional[Dict[str, Any]] = None


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    items: List[ConversationSummary]
    total: int
    page: int = 1
    page_size: int = 50


class ConversationChatResponse(BaseModel):
    """对话聊天响应"""
    message: ConversationMessage
    has_recommendation: bool = False
    conversation_id: str


class CreateConversationRequest(BaseModel):
    """创建对话请求"""
    title: str = "新的对话"


class ConversationChatRequest(BaseModel):
    """对话聊天请求"""
    content: str = Field(..., min_length=1, description="用户消息内容")


class CreateWorkflowFromConversationRequest(BaseModel):
    """从对话创建工作流请求"""
    user_id: str = "default_user"
    target_country: str = "中国"


class FileUploadResponse(BaseModel):
    """对话场景下的文件上传响应（解析交底书/技术资料）"""
    conversation_id: str
    filename: str
    file_type: str
    file_size: int
    extracted_text: str
    message_id: str
    char_count: int
    metadata: Optional[Dict[str, Any]] = None

# ==================== 系统状态 ====================

class SystemStatusResponse(BaseModel):
    """系统状态响应"""
    status: str
    active_tasks: int
    agents: List[AgentStatusResponse]
    knowledge_base_count: int
    data_sources: List[str]


class ProviderConfigResponse(BaseModel):
    """供应商配置响应（key 做掩码处理）"""
    base_url: str = ""
    model_id: str = ""
    api_key_masked: str = ""  # 显示前8位 + ****
    configured: bool = False


class ModelConfigSectionResponse(BaseModel):
    """模型配置段落"""
    active_provider: str = ""
    providers: Dict[str, ProviderConfigResponse] = {}


class SystemConfigResponse(BaseModel):
    """系统配置响应"""
    text_llm: ModelConfigSectionResponse
    image_gen: ModelConfigSectionResponse
    image_gen_fallback_to_llm: bool = False


class ProviderConfigUpdate(BaseModel):
    """更新单个供应商配置"""
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: Optional[str] = None


class ModelConfigSectionUpdate(BaseModel):
    """更新模型配置段落"""
    active_provider: Optional[str] = None
    providers: Optional[Dict[str, ProviderConfigUpdate]] = None


class SystemConfigUpdateRequest(BaseModel):
    """系统配置更新请求"""
    text_llm: Optional[ModelConfigSectionUpdate] = None
    image_gen: Optional[ModelConfigSectionUpdate] = None
