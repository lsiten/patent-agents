"""
聊天消息服务
封装聊天会话与消息的业务逻辑
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from src.repositories.unit_of_work import UnitOfWork


class ChatService:
    """聊天消息服务"""

    def __init__(
        self,
        uow_factory,
        workflow_service=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._workflow_service = workflow_service

    async def send_message(
        self,
        content: str,
        task_id: str | None = None,
        user_id: str = "default_user",
        phase: str = "initial",
    ) -> Dict[str, Any]:
        """发送聊天消息，支持头脑风暴模式和工作流模式"""
        message_id = str(uuid4())
        timestamp = datetime.now().isoformat()

        # 如果关联了工作流，交给工作流的头脑风暴 Agent 处理
        if task_id and self._workflow_service:
            workflow_ctx = self._workflow_service.get_workflow(task_id)
            if workflow_ctx:
                response = await self._workflow_service.add_chat_message(
                    task_id=task_id,
                    role="user",
                    content=content,
                )
                assistant_content = response.get("content", "消息已记录")
            else:
                assistant_content = self._generate_response(content, phase)
        else:
            assistant_content = self._generate_response(content, phase)

        return {
            "user_message": {
                "id": message_id,
                "role": "user",
                "content": content,
                "timestamp": timestamp,
            },
            "assistant_message": {
                "id": str(uuid4()),
                "role": "assistant",
                "content": assistant_content,
                "timestamp": timestamp,
                "phase": phase,
            },
        }

    async def get_chat_history(
        self,
        task_id: str | None = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """获取聊天历史"""
        if task_id and self._workflow_service:
            workflow_ctx = self._workflow_service.get_workflow(task_id)
            if workflow_ctx:
                messages = self._workflow_service.get_messages(task_id)
                return {"messages": messages, "count": len(messages)}

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

    # ── 内部辅助 ──────────────────────────────────────────

    @staticmethod
    def _generate_response(content: str, phase: str = "initial") -> str:
        """生成头脑风暴模式的智能回复"""
        responses = {
            "initial": (
                "感谢您的描述！为了更准确地评估您的专利申请方案，我想进一步了解几个关键问题：\n\n"
                "**1. 技术领域确认**\n"
                "您的发明具体属于哪个细分技术领域？（例如：人工智能/自然语言处理、半导体/芯片设计、机械/自动化设备等）\n\n"
                "**2. 现有技术痛点**\n"
                "目前行业中针对这个问题的现有解决方案有什么不足？您的发明主要改进了哪些方面？\n\n"
                "您可以先回答这两个问题，我们逐步完善信息。"
            ),
            "questioning": (
                "非常好！让我们继续完善信息：\n\n"
                "**1. 核心创新点**\n"
                "您认为这个发明最核心的创新点是什么？（可以列出1-3个关键点）\n\n"
                "**2. 技术实现细节**\n"
                "能否简要说明一下技术实现的关键步骤或原理？"
            ),
            "summarizing": (
                "太棒了！感谢您的详细说明。根据我们的沟通，我为您整理了专利申请方案摘要：\n\n"
                "📋 **专利申请方案摘要**\n\n"
                "**技术领域：** 待确认\n"
                "**核心问题：** 待确认\n"
                "**创新亮点：**\n"
                "• 创新点1\n"
                "• 创新点2\n"
                "• 创新点3\n\n"
                "**技术优势：**\n"
                "相较于现有技术，您的发明具有以下显著优势：\n"
                "- 解决了行业长期存在的技术痛点\n"
                "- 技术方案具备新颖性和创造性\n"
                "- 具有明确的商业化应用前景\n\n"
                "**建议专利类型：** 发明专利\n\n"
                "---\n\n"
                "请您确认以上信息是否准确？如有需要补充或修改的地方，请随时告诉我。确认无误后，我们可以启动正式的专利申请流程！"
            ),
        }
        return responses.get(phase, responses["initial"])
