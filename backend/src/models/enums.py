from enum import Enum


class WorkflowState(str, Enum):
    """工作流状态枚举"""
    INITIAL = "initial"
    BRAINSTORMING = "brainstorming"
    REQUIREMENT_ANALYSIS = "requirement"
    RETRIEVAL_ANALYSIS = "retrieval"
    WRITING = "writing"
    PATENT_WRITING = "patent_writing"
    REVIEWING = "reviewing"
    QUALITY_REVIEW = "quality_review"
    ITERATION = "iteration"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PatentType(str, Enum):
    """专利类型枚举"""
    INVENTION = "invention"      # 发明专利
    UTILITY = "utility"          # 实用新型
    DESIGN = "design"            # 外观设计


class AgentType(str, Enum):
    """Agent 类型枚举"""
    CEO = "ceo"
    REQUIREMENT_ANALYST = "requirement_analyst"
    RETRIEVAL_ANALYST = "retrieval_analyst"
    PATENT_WRITER = "patent_writer"
    QUALITY_REVIEWER = "quality_reviewer"


class AgentStatus(str, Enum):
    """Agent 状态枚举"""
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    ERROR = "error"


class Severity(str, Enum):
    """严重程度枚举"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Rating(str, Enum):
    """评级枚举"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
