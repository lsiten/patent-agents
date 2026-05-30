"""
Hermes Agent 工具层

保留 21 个专利工具实现 + adapter 桥接到 hermes-agent registry。
旧的 base/memory/profiles 已移除，由 run_agent.AIAgent 替代。
"""

from .tools import init_patent_tools

__all__ = [
    "init_patent_tools",
]
