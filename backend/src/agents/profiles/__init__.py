"""
Agent Profiles 模块
定义和管理专利申请系统的所有专业 Agent Profile
"""

from .default_profiles import (
    register_default_profiles,
    create_ceo_agent_profile,
    create_requirement_analyst_profile,
    create_retrieval_analyst_profile,
    create_patent_writer_profile,
    create_quality_reviewer_profile,
    create_brainstorm_partner_profile,
)
from ..hermes.profiles import ProfileRegistry

__all__ = [
    "ProfileRegistry",
    "register_default_profiles",
    "create_ceo_agent_profile",
    "create_requirement_analyst_profile",
    "create_retrieval_analyst_profile",
    "create_patent_writer_profile",
    "create_quality_reviewer_profile",
    "create_brainstorm_partner_profile",
]
