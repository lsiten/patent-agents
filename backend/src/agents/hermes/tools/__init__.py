"""
Hermes 工具模块

工具通过 adapter.py 注册到 hermes-agent 的全局 registry（toolset="patent"）。
AIAgent 实例化时通过 enabled_toolsets=["patent"] 启用所有专利工具。
"""

from .adapter import init_patent_tools

__all__ = [
    "init_patent_tools",
]
