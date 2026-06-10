from __future__ import annotations

"""
Chat endpoint tests.
"""

import pytest
from fastapi import BackgroundTasks
import asyncio
import json
import time
from datetime import datetime
from typing import AsyncGenerator, cast

from src.api import routes
from src.api.schemas import AgentEventInfo, ConversationChatRequest
from src.core.workflow_engine import WorkflowContext, WorkflowState


class TestAgentActivityEvents:
    def test_agent_event_info_serializes_canonical_identity_fields(self):
        event = AgentEventInfo(
            id="evt-001",
            sequence=1,
            call_id="call-001",
            type="thinking",
            agent_name="patent.ceo.v1",
            timestamp="2026-06-06T02:00:00",
            message="正在分析技术方案",
            data={"message": "正在分析技术方案"},
        )

        payload = event.model_dump()

        assert payload["id"] == "evt-001"
        assert payload["sequence"] == 1
        assert payload["call_id"] == "call-001"
        assert payload["type"] == "thinking"
        assert payload["data"] == {"message": "正在分析技术方案"}

    def test_agent_event_info_backfills_legacy_identity_fields(self):
        event = AgentEventInfo(
            type="status",
            agent_name="patent.ceo.v1",
            timestamp="2026-06-06T02:00:00",
            message="旧日志事件",
            data={"kind": "legacy"},
        )

        payload = event.model_dump()

        assert payload["id"] == "legacy-status-2026-06-06T02:00:00"
        assert payload["sequence"] == 0
        assert payload["call_id"] == "legacy"

    def test_agent_activity_event_builder_preserves_order_and_call_id(self):
        first = routes._build_agent_activity_event(
            event_type="tool_call_start",
            agent_name="patent.ceo.v1",
            sequence=1,
            call_id="tool-call-1",
            message="调用工具: patent_search",
            data={"name": "patent_search"},
            event_id="evt-start",
        )
        second = routes._build_agent_activity_event(
            event_type="tool_call_end",
            agent_name="patent.ceo.v1",
            sequence=2,
            call_id="tool-call-1",
            message="工具完成: patent_search",
            data={"name": "patent_search", "success": True},
            event_id="evt-end",
        )

        assert [first["sequence"], second["sequence"]] == [1, 2]
        assert first["call_id"] == second["call_id"] == "tool-call-1"
        assert first["id"] == "evt-start"
        assert second["id"] == "evt-end"
        assert second["data"]["success"] is True

    def test_agent_activity_event_can_be_sent_as_canonical_sse_payload(self):
        event = routes._build_agent_activity_event(
            event_type="thinking",
            agent_name="patent.ceo.v1",
            sequence=3,
            call_id="stream-call-1",
            message="正在归纳创新点",
            data={"agent": "patent.ceo.v1", "message": "正在归纳创新点"},
            event_id="evt-thinking",
        )

        sse_payload = {"type": "agent_activity", "data": event}

        assert sse_payload["type"] == "agent_activity"
        assert sse_payload["data"]["id"] == "evt-thinking"
        assert sse_payload["data"]["sequence"] == 3
        assert sse_payload["data"]["call_id"] == "stream-call-1"
        assert sse_payload["data"]["message"] == "正在归纳创新点"

    def test_conversation_stream_emits_and_persists_canonical_agent_activity(
        self,
        client,
        api_prefix,
        monkeypatch,
    ):
        conv_id = "conv-agent-activity-stream"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "新的对话",
            "messages": [],
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "linked_workflow_id": None,
        }

        class FakeAgent:
            def __init__(self, callbacks):
                self.callbacks = callbacks

            def run_conversation(self, prompt):
                self.callbacks["thinking"]("正在分析用户的技术方案")
                self.callbacks["tool_start"]("tool-call-abc", "patent_search", {"query": "test"})
                self.callbacks["tool_complete"]("tool-call-abc", "patent_search", {}, "检索完成")
                self.callbacks["status"]("lifecycle", "正在生成回复")
                return {"final_response": "这是整理后的答复"}

        def fake_create_ai_agent(*, profile_id, session_id, callbacks):
            return FakeAgent(callbacks)

        monkeypatch.setattr(routes, "create_ai_agent", fake_create_ai_agent)

        with client.stream(
            "POST",
            f"{api_prefix}/conversations/{conv_id}/chat/stream",
            json={"content": "请分析这个方案"},
        ) as response:
            body = "".join(response.iter_text())

        agent_activity_events = []
        for block in body.split("\n\n"):
            if block.startswith("event: agent_activity"):
                data_line = next(line for line in block.splitlines() if line.startswith("data: "))
                agent_activity_events.append(json.loads(data_line.removeprefix("data: ")))

        assert response.status_code == 200, body
        assert [event["sequence"] for event in agent_activity_events] == [1, 2, 3, 4]
        assert all(event["id"] for event in agent_activity_events)
        assert agent_activity_events[1]["call_id"] == "tool-call-abc"
        assert agent_activity_events[2]["call_id"] == "tool-call-abc"

        persisted = routes.conversations_store[conv_id]["messages"][-1]
        assert persisted["role"] == "assistant"
        assert persisted["agent_events"] == agent_activity_events

    def test_conversation_stream_bridges_specialist_agent_activity(
        self,
        client,
        api_prefix,
        monkeypatch,
    ):
        conv_id = "conv-specialist-agent-activity-stream"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "新的对话",
            "messages": [],
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "linked_workflow_id": None,
        }

        class FakeCeoAgent:
            def run_conversation(self, prompt):
                import asyncio

                from src.agents.hermes.tools.dispatch_specialist import DispatchSpecialistTool

                asyncio.run(
                    DispatchSpecialistTool().execute(
                        agent_id="requirement_analyst",
                        task="分析技术方案并提取创新点",
                    )
                )
                return {"final_response": "已完成专业分析"}

        class FakeSpecialistAgent:
            def __init__(self, callbacks):
                self.callbacks = callbacks or {}

            def run_conversation(self, prompt):
                if "thinking" in self.callbacks:
                    self.callbacks["thinking"]("正在拆解技术方案")
                if "status" in self.callbacks:
                    self.callbacks["status"]("lifecycle", "正在提取创新点")
                return {"final_response": "结构化需求分析结果"}

        def fake_route_create_ai_agent(*, profile_id, session_id, callbacks):
            return FakeCeoAgent()

        def fake_agent_config_create_ai_agent(profile_id, *args, **kwargs):
            return FakeSpecialistAgent(kwargs.get("callbacks"))

        monkeypatch.setattr(routes, "create_ai_agent", fake_route_create_ai_agent)

        import src.agents.agent_config as agent_config

        monkeypatch.setattr(agent_config, "create_ai_agent", fake_agent_config_create_ai_agent)

        with client.stream(
            "POST",
            f"{api_prefix}/conversations/{conv_id}/chat/stream",
            json={"content": "请分析这个方案"},
        ) as response:
            body = "".join(response.iter_text())

        agent_activity_events = []
        for block in body.split("\n\n"):
            if block.startswith("event: agent_activity"):
                data_line = next(line for line in block.splitlines() if line.startswith("data: "))
                agent_activity_events.append(json.loads(data_line.removeprefix("data: ")))

        assert response.status_code == 200, body
        assert any(event["agent_name"] == "需求分析师" for event in agent_activity_events)
        assert any(
            event["agent_name"] == "需求分析师" and "正在拆解技术方案" in event["message"]
            for event in agent_activity_events
        )

        persisted = routes.conversations_store[conv_id]["messages"][-1]
        assert any(event["agent_name"] == "需求分析师" for event in persisted["agent_events"])

    def test_conversation_stream_emits_heartbeat_when_agent_is_quiet(
        self,
        client,
        api_prefix,
        monkeypatch,
    ):
        conv_id = "conv-quiet-agent-stream"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "新的对话",
            "messages": [],
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "linked_workflow_id": None,
        }

        class QuietAgent:
            def run_conversation(self, prompt):
                time.sleep(0.2)
                return {"final_response": "安静运行后的答复"}

        def fake_create_ai_agent(*, profile_id, session_id, callbacks):
            return QuietAgent()

        monkeypatch.setattr(routes, "create_ai_agent", fake_create_ai_agent)
        monkeypatch.setattr(routes, "CONVERSATION_STREAM_HEARTBEAT_SECONDS", 0.01, raising=False)

        with client.stream(
            "POST",
            f"{api_prefix}/conversations/{conv_id}/chat/stream",
            json={"content": "请分析这个方案"},
        ) as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200, body
        assert "event: heartbeat" in body
        assert "安静运行后的答复" in body

    async def test_conversation_stream_persists_assistant_after_client_disconnect(
        self,
        monkeypatch,
    ):
        conv_id = "conv-disconnect-persists-assistant"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "新的对话",
            "messages": [],
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "linked_workflow_id": None,
        }

        class SlowAgent:
            def run_conversation(self, prompt):
                time.sleep(0.1)
                return {"final_response": "断开连接后仍应保存的答复"}

        def fake_create_ai_agent(*, profile_id, session_id, callbacks):
            return SlowAgent()

        monkeypatch.setattr(routes, "create_ai_agent", fake_create_ai_agent)
        monkeypatch.setattr(routes, "CONVERSATION_STREAM_HEARTBEAT_SECONDS", 0.01, raising=False)

        response = await routes.chat_in_conversation_stream(
            conv_id,
            ConversationChatRequest(content="请分析这个方案"),
        )
        body_iterator = cast(AsyncGenerator[str, None], response.body_iterator)
        async for chunk in body_iterator:
            if "event: heartbeat" in chunk:
                await body_iterator.aclose()
                break

        await asyncio.sleep(0.2)

        messages = routes.conversations_store[conv_id]["messages"]
        assert any(
            message["role"] == "assistant" and message["content"] == "断开连接后仍应保存的答复"
            for message in messages
        )

    def test_conversation_stream_recommends_workflow_after_full_flow_analysis(
        self,
        client,
        api_prefix,
        monkeypatch,
    ):
        conv_id = "conv-full-flow-analysis-recommendation"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "完整流程申请",
            "messages": [
                {
                    "id": "msg-user-full-flow",
                    "role": "user",
                    "content": "请基于以下技术方案生成完整发明专利申请文件，并执行需求分析、现有技术检索、专利撰写、附图生成和质量审查全流程。",
                    "timestamp": now,
                    "type": "text",
                    "metadata": None,
                },
                {
                    "id": "msg-assistant-confirm",
                    "role": "assistant",
                    "content": "请确认系统、方法、边缘控制装置是否均支持。",
                    "timestamp": now,
                    "type": "text",
                    "metadata": None,
                },
            ],
            "created_at": now,
            "updated_at": now,
            "status": "brainstorming",
            "linked_workflow_id": None,
        }

        class FullFlowAgent:
            def __init__(self, callbacks):
                self.callbacks = callbacks

            def run_conversation(self, prompt):
                self.callbacks["tool_complete"](
                    "call-requirements",
                    "dispatch_specialist",
                    {},
                    '{"agent_id":"requirement_analyst","result":"需求分析完成"}',
                )
                self.callbacks["tool_complete"](
                    "call-retrieval",
                    "dispatch_specialist",
                    {},
                    '{"agent_id":"retrieval_analyst","result":"检索分析完成"}',
                )
                return {
                    "final_response": "检索结论已完成，建议围绕蒸腾需求差值驱动滴灌量二次修正撰写申请文件。"
                }

        def fake_create_ai_agent(*, profile_id, session_id, callbacks):
            return FullFlowAgent(callbacks)

        monkeypatch.setattr(routes, "create_ai_agent", fake_create_ai_agent)

        with client.stream(
            "POST",
            f"{api_prefix}/conversations/{conv_id}/chat/stream",
            json={"content": "两者均支持"},
        ) as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200, body
        assert '"has_recommendation": true' in body
        persisted = routes.conversations_store[conv_id]["messages"][-1]
        assert persisted["metadata"] == {"recommend_create_patent": True}


class TestChat:
    def test_chat_with_message(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/chat/messages",
            json={"content": "What is patent eligibility?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should contain user_message and assistant_message
        assert "user_message" in data
        assert "assistant_message" in data

    def test_chat_with_history(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/chat/messages",
            json={
                "content": "Explain prior art",
                "user_id": "test_user",
            },
        )
        assert response.status_code == 200

    def test_chat_missing_content(self, client, api_prefix):
        response = client.post(f"{api_prefix}/chat/messages", json={})
        assert response.status_code == 422
        errors = response.json().get("detail", [])
        assert any("content" in str(e) for e in errors)

    def test_chat_empty_content(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/chat/messages",
            json={"content": ""},
        )
        # Should reject empty content with 422
        assert response.status_code == 422


class TestBrainstorm:
    def test_brainstorm_with_message(self, client, api_prefix):
        session_id = "test_brainstorm_session"
        response = client.post(
            f"{api_prefix}/chat/messages",
            json={"content": "Brainstorm patent ideas for AI in healthcare"},
            params={"phase": "initial"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_brainstorm_missing_content(self, client, api_prefix):
        response = client.post(f"{api_prefix}/chat/messages", json={})
        assert response.status_code == 422


class TestConversationWorkflowLinking:
    def test_create_workflow_from_conversation_auto_starts_workflow(
        self,
        client,
        api_prefix,
        monkeypatch,
    ):
        conv_id = "conv-auto-start-workflow"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "自动启动工作流对话",
            "messages": [
                {
                    "id": "msg-user-1",
                    "role": "user",
                    "content": "一种基于可折叠Cave屏幕的视频画面自适应处理方法，能够根据屏幕角度自动裁切和映射画面。",
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
        executed = []

        async def fake_execute_full_workflow(
            context: WorkflowContext,
            phase_callback=None,
            event_callback=None,
        ) -> WorkflowContext:
            executed.append(context.task_id)
            context.current_phase = WorkflowState.REQUIREMENT_ANALYSIS
            return context

        monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

        response = client.post(
            f"{api_prefix}/conversations/{conv_id}/create-workflow",
            json={"user_id": "default_user", "target_country": "中国"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "started"
        assert executed == [data["task_id"]]
        assert any(
            event.event_type == "workflow.started"
            for event in routes.task_events[data["task_id"]]
        )

    async def test_create_workflow_from_conversation_marks_queryable_workflow_as_started_before_background_runs(
        self,
    ):
        conv_id = "conv-queryable-started-workflow"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "可查询启动状态对话",
            "messages": [
                {
                    "id": "msg-user-1",
                    "role": "user",
                    "content": "一种基于可折叠Cave屏幕的视频画面自适应处理方法，能够根据屏幕角度自动裁切和映射画面。",
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
        background_tasks = BackgroundTasks()

        result = await routes.create_workflow_from_conversation(
            conv_id,
            routes.CreateWorkflowFromConversationRequest(user_id="default_user", target_country="中国"),
            background_tasks,
        )

        assert result["status"] == "started"
        assert len(background_tasks.tasks) == 1
        workflow = await routes.get_workflow(result["task_id"])
        assert workflow.current_state == WorkflowState.REQUIREMENT_ANALYSIS.value

    def test_create_workflow_from_linked_conversation_returns_existing_workflow(
        self,
        client,
        api_prefix,
    ):
        conv_id = "conv-already-linked-workflow"
        workflow_id = "workflow-existing-link"
        now = datetime.now().isoformat()
        routes.conversations_store[conv_id] = {
            "id": conv_id,
            "title": "已关联工作流对话",
            "messages": [
                {
                    "id": "msg-user-1",
                    "role": "user",
                    "content": "一种用于动态调度多智能体专利撰写流程的方法",
                    "timestamp": now,
                    "type": "text",
                    "metadata": None,
                }
            ],
            "created_at": now,
            "updated_at": now,
            "status": "workflow_linked",
            "linked_workflow_id": workflow_id,
        }

        response = client.post(
            f"{api_prefix}/conversations/{conv_id}/create-workflow",
            json={"user_id": "default_user", "target_country": "中国"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "task_id": workflow_id,
            "status": "already_linked",
            "conversation_id": conv_id,
        }


class TestAnalyze:
    def test_analyze_with_message(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/chat/messages",
            json={"content": "Analyze this invention: a new type of battery"},
            params={"phase": "questioning"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_analyze_missing_content(self, client, api_prefix):
        response = client.post(f"{api_prefix}/chat/messages", json={})
        assert response.status_code == 422
