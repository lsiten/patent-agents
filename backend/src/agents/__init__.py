"""
专利申请多智能体系统 - Agent 层
基于 hermes-agent (run_agent.AIAgent) 架构

旧的 HermesAgent / ProfileRegistry / MemoryStore 已移除。
新架构通过 hermes_agent_service.py 提供统一服务。
"""

from .hermes_agent_service import get_hermes_agent_service

__all__ = [
    "get_hermes_agent_service",
]
