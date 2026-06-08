from __future__ import annotations

import pytest

from src.api import routes
from src.core.workflow_engine import PatentWorkflowEngine


@pytest.fixture(autouse=True)
def clear_route_state():
    routes.conversations_store.clear()
    routes.conversation_event_queues.clear()
    routes.task_events.clear()
    yield
    routes.conversations_store.clear()
    routes.conversation_event_queues.clear()
    routes.task_events.clear()


class FakeHermesService:
    async def run_conversation_stream(self, profile_id: str, user_input: str, session_id: str | None = None, user_id: str | None = None):
        yield {
            "type": "tool_call_start",
            "data": {
                "name": "dispatch_specialist",
                "parameters": {
                    "agent_id": "requirement_analyst",
                    "task": "分析技术方案并提取创新点",
                },
            },
        }
        yield {
            "type": "tool_call_end",
            "data": {
                "name": "dispatch_specialist",
                "parameters": {
                    "agent_id": "requirement_analyst",
                    "task": "分析技术方案并提取创新点",
                },
                "result": {
                    "agent": "需求分析师",
                    "agent_id": "requirement_analyst",
                    "profile_id": "patent.requirement_analyst.v1",
                    "task": "分析技术方案并提取创新点",
                    "result": "已提取核心创新点",
                    "status": "completed",
                },
                "success": True,
            },
        }
        yield {"type": "content", "data": {"content": "CEO 汇总", "has_recommendation": False}}
        yield {"type": "done", "data": {}}


class FailingHermesService:
    async def run_conversation_stream(self, profile_id: str, user_input: str, session_id: str | None = None, user_id: str | None = None):
        yield {
            "type": "tool_call_start",
            "data": {
                "name": "dispatch_specialist",
                "parameters": {
                    "agent_id": "retrieval_analyst",
                    "task": "检索先有技术",
                },
            },
        }
        yield {
            "type": "tool_call_end",
            "data": {
                "name": "dispatch_specialist",
                "parameters": {
                    "agent_id": "retrieval_analyst",
                    "task": "检索先有技术",
                },
                "result": {
                    "agent": "检索分析师",
                    "agent_id": "retrieval_analyst",
                    "profile_id": "patent.retrieval_analyst.v1",
                    "task": "检索先有技术",
                    "error": "检索服务不可用",
                    "status": "failed",
                },
                "success": False,
                "error": "检索服务不可用",
            },
        }
        yield {"type": "content", "data": {"content": "CEO 汇总", "has_recommendation": False}}
        yield {"type": "done", "data": {}}


@pytest.mark.asyncio
async def test_workflow_agent_event_callback_started(monkeypatch):
    engine = PatentWorkflowEngine()
    context = engine.create_workflow(
        task_id="workflow-agent-callback",
        user_id="user-1",
        description="一种智能专利撰写系统",
    )
    received = []

    monkeypatch.setattr("src.core.workflow_engine._get_agent_factory", lambda: FakeHermesService())

    await engine.execute_full_workflow(context, agent_event_callback=received.append)

    assert received[0]["event_type"] == "agent.work.started"
    assert received[0]["agent_id"] == "requirement_analyst"
    assert received[0]["agent_name"] == "需求分析师"
    assert received[0]["action"] == "分析技术方案并提取创新点"
    assert received[0]["status"] == "running"
    assert any(event["event_type"] == "agent.work.completed" for event in received)


def test_create_workflow_persists_agent_started_and_completed_messages(client, api_prefix, monkeypatch):
    async def fake_execute_full_workflow(context, phase_callback=None, agent_event_callback=None):
        assert agent_event_callback is not None
        await agent_event_callback({
            "event_type": "agent.work.started",
            "task_id": context.task_id,
            "agent_id": "requirement_analyst",
            "agent_name": "需求分析师",
            "profile_id": "patent.requirement_analyst.v1",
            "action": "分析技术方案并提取创新点",
            "status": "running",
            "data": {"task": "分析技术方案并提取创新点"},
        })
        await agent_event_callback({
            "event_type": "agent.work.completed",
            "task_id": context.task_id,
            "agent_id": "requirement_analyst",
            "agent_name": "需求分析师",
            "profile_id": "patent.requirement_analyst.v1",
            "action": "分析技术方案并提取创新点",
            "status": "completed",
            "summary": "已提取核心创新点",
            "data": {"task": "分析技术方案并提取创新点"},
        })
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    created = client.post(f"{api_prefix}/conversations", json={"title": "测试对话"})
    conv_id = created.json()["id"]
    routes.conversations_store[conv_id]["messages"].append({
        "id": "user-message",
        "role": "user",
        "content": "一种智能专利撰写系统",
        "timestamp": "2026-06-08T00:00:00",
        "type": "text",
        "metadata": None,
    })

    response = client.post(f"{api_prefix}/conversations/{conv_id}/create-workflow", json={})

    assert response.status_code == 200
    messages = routes.conversations_store[conv_id]["messages"]
    progress_messages = [message for message in messages if message.get("role") == "agent"]
    assert [message["metadata"]["status"] for message in progress_messages] == ["running", "completed"]
    assert progress_messages[0]["agent_name"] == "需求分析师"
    assert "分析技术方案并提取创新点" in progress_messages[0]["content"]


def test_failed_agent_work_event_is_persisted_and_streamed(client, api_prefix, monkeypatch):
    async def fake_execute_full_workflow(context, phase_callback=None, agent_event_callback=None):
        assert agent_event_callback is not None
        await agent_event_callback({
            "event_type": "agent.work.failed",
            "task_id": context.task_id,
            "agent_id": "retrieval_analyst",
            "agent_name": "检索分析师",
            "profile_id": "patent.retrieval_analyst.v1",
            "action": "检索先有技术",
            "status": "failed",
            "error": "检索服务不可用",
            "data": {"task": "检索先有技术"},
        })
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    created = client.post(f"{api_prefix}/conversations", json={"title": "失败对话"})
    conv_id = created.json()["id"]
    routes.conversations_store[conv_id]["messages"].append({
        "id": "user-message",
        "role": "user",
        "content": "一种智能专利撰写系统",
        "timestamp": "2026-06-08T00:00:00",
        "type": "text",
        "metadata": None,
    })

    response = client.post(f"{api_prefix}/conversations/{conv_id}/create-workflow", json={})

    assert response.status_code == 200
    failed_messages = [
        message for message in routes.conversations_store[conv_id]["messages"]
        if (message.get("metadata") or {}).get("status") == "failed"
    ]
    assert failed_messages[0]["agent_name"] == "检索分析师"
    assert "检索服务不可用" in failed_messages[0]["content"]


def test_conversation_event_stream_emits_agent_work(client, api_prefix):
    created = client.post(f"{api_prefix}/conversations", json={"title": "流式对话"})
    conv_id = created.json()["id"]
    routes.conversation_event_queues[conv_id] = [
        {
            "type": "agent_work",
            "data": {
                "event_type": "agent.work.started",
                "task_id": "task-1",
                "conversation_id": conv_id,
                "agent_id": "requirement_analyst",
                "agent_name": "需求分析师",
                "action": "分析技术方案并提取创新点",
                "status": "running",
                "timestamp": "2026-06-08T00:00:00",
            },
        }
    ]

    with client.stream("GET", f"{api_prefix}/conversations/{conv_id}/events/stream") as response:
        body = next(response.iter_text())

    assert response.status_code == 200
    assert "event: agent_work" in body
    assert "需求分析师" in body



def test_direct_workflow_start_records_agent_events_without_conversation(client, api_prefix, monkeypatch):
    async def fake_execute_full_workflow(context, phase_callback=None, agent_event_callback=None):
        assert agent_event_callback is not None
        await agent_event_callback({
            "event_type": "agent.work.started",
            "task_id": context.task_id,
            "agent_id": "requirement_analyst",
            "agent_name": "需求分析师",
            "profile_id": "patent.requirement_analyst.v1",
            "action": "分析技术方案并提取创新点",
            "status": "running",
            "data": {"task": "分析技术方案并提取创新点"},
        })
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    created = client.post(
        f"{api_prefix}/workflows",
        json={"tech_description": "一种基于多智能体协作的智能专利撰写系统和方法", "user_id": "default_user"},
    )
    task_id = created.json()["task_id"]

    response = client.post(f"{api_prefix}/workflows/{task_id}/start")

    assert response.status_code == 200
    events = routes.task_events[task_id]
    assert any(event.event_type == "agent.work.started" for event in events)
    assert routes.conversation_event_queues == {}


def test_conversation_event_stream_consumes_queue(client, api_prefix):
    created = client.post(f"{api_prefix}/conversations", json={"title": "清理流式对话"})
    conv_id = created.json()["id"]
    routes.conversation_event_queues[conv_id] = [
        {"type": "agent_work", "data": {"agent_name": "需求分析师", "action": "分析技术方案"}}
    ]

    with client.stream("GET", f"{api_prefix}/conversations/{conv_id}/events/stream") as response:
        body = next(response.iter_text())

    assert response.status_code == 200
    assert "event: agent_work" in body
    assert conv_id not in routes.conversation_event_queues


def test_delete_conversation_clears_event_queue(client, api_prefix, monkeypatch):
    class FakeStore:
        async def delete(self, collection, key):
            return None

    monkeypatch.setattr(routes, "_get_persist_store", lambda: FakeStore())

    created = client.post(f"{api_prefix}/conversations", json={"title": "删除流式对话"})
    conv_id = created.json()["id"]
    routes.conversation_event_queues[conv_id] = [
        {"type": "agent_work", "data": {"agent_name": "需求分析师"}}
    ]

    response = client.delete(f"{api_prefix}/conversations/{conv_id}")

    assert response.status_code == 204
    assert conv_id not in routes.conversations_store
    assert conv_id not in routes.conversation_event_queues
