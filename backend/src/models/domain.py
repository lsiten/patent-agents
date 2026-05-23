from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .enums import WorkflowState, PatentType, Severity, Rating


# ==================== 核心任务模型 ====================

class PatentTask(BaseModel):
    """专利申请任务"""
    task_id: str
    user_id: str
    tech_description: str
    patent_type_preference: Optional[PatentType] = None
    current_state: WorkflowState = WorkflowState.INITIAL
    iteration_count: int = 0
    max_iterations: int = 3
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # 各阶段输出
    requirement_doc: Optional["RequirementDoc"] = None
    retrieval_report: Optional["RetrievalReport"] = None
    draft_doc: Optional["PatentDraft"] = None
    review_report: Optional["ReviewReport"] = None
    final_patent: Optional["FinalPatent"] = None


# ==================== 需求分析阶段 ====================

class KeyFeature(BaseModel):
    """关键技术特征"""
    name: str
    description: str
    is_innovative: bool = False
    implementation_hint: Optional[str] = None


class RequirementDoc(BaseModel):
    """结构化技术需求文档"""
    tech_field: str  # 技术领域
    ipc_classification: Optional[List[str]] = None  # IPC分类号建议
    core_principle: str  # 核心原理
    application_scenarios: List[str]  # 应用场景
    technical_problem: str  # 解决的技术问题
    technical_solution_summary: str  # 技术方案概述
    key_features: List[KeyFeature]  # 关键技术特征
    patent_type_recommendation: PatentType
    recommendation_rationale: str  # 推荐理由
    beneficial_effects: List[str]  # 有益效果
    information_gaps: List[str] = Field(default_factory=list)  # 信息缺口
    reference_patent_ids: List[str] = Field(default_factory=list)  # 参考专利ID
    analysis_confidence: float = Field(default=0.8, ge=0, le=1)  # 分析置信度


# ==================== 检索分析阶段 ====================

class PriorArtReference(BaseModel):
    """现有技术参考文献"""
    reference_id: str  # 专利号或文献ID
    title: str
    publication_date: Optional[str] = None
    applicant: Optional[str] = None
    abstract: str
    similarity_score: float = Field(ge=0, le=1)
    key_claims: List[str] = Field(default_factory=list)
    technical_differences: List[str] = Field(default_factory=list)  # 与本发明的区别
    url: Optional[str] = None
    source: str  # 数据来源: cnipa/uspto/epo/google_scholar/arxiv等


class RetrievalReport(BaseModel):
    """检索分析报告"""
    novelty_assessment: Rating
    novelty_rationale: str
    inventive_step_assessment: Rating
    inventive_step_rationale: str
    utility_assessment: Rating
    utility_rationale: str
    overall_patentability: Rating
    overall_confidence: float = Field(ge=0, le=1)

    prior_art_found: List[PriorArtReference] = Field(default_factory=list)
    high_risk_references: List[PriorArtReference] = Field(default_factory=list)

    writing_recommendations: List[str] = Field(default_factory=list)
    claim_strategy_recommendations: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)

    retrieval_databases: List[str] = Field(default_factory=list)  # 检索的数据库
    retrieval_keywords: List[str] = Field(default_factory=list)  # 检索关键词
    reference_patent_ids: List[str] = Field(default_factory=list)  # 相似参考专利ID


# ==================== 专利撰写阶段 ====================

class Claim(BaseModel):
    """权利要求"""
    claim_number: int
    claim_type: str  # independent/dependent
    content: str
    dependencies: List[int] = Field(default_factory=list)
    category: Optional[str] = None  # 产品/方法/用途


class DescriptionSection(BaseModel):
    """说明书章节"""
    section_name: str
    content: str
    word_count: int = 0


class PatentDraft(BaseModel):
    """专利申请文件草稿"""
    title: str
    technical_field: str
    background_art: DescriptionSection
    summary_of_invention: DescriptionSection  # 发明内容
    description_of_drawings: Optional[DescriptionSection] = None  # 附图说明
    detailed_description: DescriptionSection  # 具体实施方式
    claims: List[Claim]
    abstract: str
    key_terms_dictionary: Dict[str, str] = Field(default_factory=dict)

    # 格式规范信息
    format_version: str = "2024"
    word_count: int = 0
    reference_patent_style_ids: List[str] = Field(default_factory=list)  # 参考的定稿专利ID

    # 生成元数据
    generated_at: datetime = Field(default_factory=datetime.now)
    generation_model: Optional[str] = None


# ==================== 质量审查阶段 ====================

class ReviewIssue(BaseModel):
    """审查问题"""
    issue_id: str
    severity: Severity
    location: str  # 位置描述
    issue_type: str  # 问题类型
    description: str
    suggestion: str
    related_clause: Optional[str] = None  # 相关法条


class ReviewResult(BaseModel):
    """单项审查结果"""
    passed: bool
    score: float = Field(ge=0, le=1)
    issues: List[ReviewIssue] = Field(default_factory=list)


class ReviewReport(BaseModel):
    """质量审查报告"""
    formal_compliance: ReviewResult  # 形式合规审查
    claims_review: ReviewResult  # 权利要求书审查
    description_review: ReviewResult  # 说明书审查
    consistency_review: ReviewResult  # 一致性审查
    prior_art_risk: ReviewResult  # 现有技术风险审查

    overall_score: float = Field(ge=0, le=1)
    recommendation: str  # approve/revise/reject
    revision_priority: Severity
    estimated_office_action_risk: float = Field(ge=0, le=1)  # 审查意见风险预估

    examiner_comments: List[str] = Field(default_factory=list)
    improvement_suggestions: List[str] = Field(default_factory=list)

    reviewed_at: datetime = Field(default_factory=datetime.now)


# ==================== 最终交付 ====================

class FinalPatent(BaseModel):
    """最终专利交付包"""
    task_id: str
    patent_draft: PatentDraft
    review_report: ReviewReport
    retrieval_report: RetrievalReport

    # 导出格式
    docx_url: Optional[str] = None
    pdf_url: Optional[str] = None
    json_url: Optional[str] = None

    # 元数据
    generated_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0"
    quality_score: float = Field(ge=0, le=1)


# ==================== 定稿知识库 ====================

class FinalizedPatent(BaseModel):
    """已定稿专利 - 作为知识库和风格参考"""
    patent_id: str
    title: str
    patent_number: Optional[str] = None  # 实际专利号
    application_date: Optional[datetime] = None
    tech_field: str
    ipc_classification: List[str] = Field(default_factory=list)

    # 文件内容
    claims: List[Claim]
    description_sections: List[DescriptionSection]
    abstract: str

    # 风格特征提取
    style_features: Dict[str, Any] = Field(default_factory=dict)
    writing_patterns: List[str] = Field(default_factory=list)
    standard_terms: List[str] = Field(default_factory=list)

    # 质量标签
    quality_score: Optional[float] = None
    is_exemplar: bool = False  # 是否作为范例

    created_at: datetime = Field(default_factory=datetime.now)
    source: str  # 来源：internal/upload/official
    tags: List[str] = Field(default_factory=list)


# ==================== 外部数据源模型 ====================

class DataSourceConfig(BaseModel):
    """数据源配置"""
    source_id: str
    name: str
    source_type: str  # patent/academic/legal
    base_url: str
    enabled: bool = True
    rate_limit: int = 60  # 请求/分钟
    auth_required: bool = False
    credentials_env: Optional[Dict[str, str]] = None  # 环境变量名映射


class SearchQuery(BaseModel):
    """检索查询"""
    query: str
    tech_field: Optional[str] = None
    ipc_class: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_results: int = 20
    databases: List[str] = Field(default_factory=list)


# ==================== 工作流事件 ====================

class WorkflowEvent(BaseModel):
    """工作流事件"""
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    agent: str
    message: str
    event_type: str  # info/progress/success/warning/error
    data: Optional[Dict[str, Any]] = None
