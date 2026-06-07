from __future__ import annotations

from datetime import datetime
import json
import asyncio

import pytest

from src.api import routes
from src.core.workflow_engine import PhaseResult, WorkflowPhase


@pytest.fixture(autouse=True)
def clear_linked_workflow_state():
    routes.conversations_store.clear()
    routes.task_events.clear()
    routes.workflow_engine._running_workflows.clear()
    yield
    routes.conversations_store.clear()
    routes.task_events.clear()
    routes.workflow_engine._running_workflows.clear()


def _linked_conversation(conv_id: str, task_id: str) -> None:
    now = datetime.now().isoformat()
    routes.conversations_store[conv_id] = {
        "id": conv_id,
        "title": "Linked workflow conversation",
        "messages": [],
        "created_at": now,
        "updated_at": now,
        "status": "workflow_linked",
        "linked_workflow_id": task_id,
    }
    routes.workflow_engine.create_workflow(
        task_id=task_id,
        user_id="test_user",
        description="Original invention description",
    )
    routes.task_events[task_id] = []


async def _fake_workflow_chat(task_id: str, role: str, content: str):
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    context.add_message(role, content)
    context.add_message("assistant", f"已同步到工作流：{content}")
    return {
        "role": "assistant",
        "content": f"已同步到工作流：{content}",
        "phase": context.current_phase.value,
    }


def test_linked_conversation_chat_routes_to_workflow(client, api_prefix, monkeypatch):
    conv_id = "conv-linked-chat"
    task_id = "task-linked-chat"
    _linked_conversation(conv_id, task_id)
    monkeypatch.setattr(routes.workflow_engine, "add_chat_message", _fake_workflow_chat)

    response = client.post(
        f"{api_prefix}/conversations/{conv_id}/chat",
        json={"content": "补充可调屏幕角度映射关系"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["conversation_id"] == conv_id
    assert data["message"]["content"] == "已同步到工作流：补充可调屏幕角度映射关系"
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    assert any(m["role"] == "user" and m["content"] == "补充可调屏幕角度映射关系" for m in context.message_history)
    assert any(e.event_type == "chat.message.created" for e in routes.task_events[task_id])


def test_linked_conversation_stream_routes_to_workflow(client, api_prefix, monkeypatch):
    conv_id = "conv-linked-stream"
    task_id = "task-linked-stream"
    _linked_conversation(conv_id, task_id)
    monkeypatch.setattr(routes.workflow_engine, "add_chat_message", _fake_workflow_chat)

    with client.stream(
        "POST",
        f"{api_prefix}/conversations/{conv_id}/chat/stream",
        json={"content": "补充遮挡画面删除策略"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200, body
    assert "该对话已关联工作流" not in body
    assert "event: content" in body
    assert "event: done" in body
    assert "已同步到工作流：补充遮挡画面删除策略" in body
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    assert any(m["role"] == "user" and m["content"] == "补充遮挡画面删除策略" for m in context.message_history)


def test_linked_conversation_stream_emits_heartbeat_while_workflow_is_quiet(
    client, api_prefix, monkeypatch
):
    conv_id = "conv-linked-quiet-stream"
    task_id = "task-linked-quiet-stream"
    _linked_conversation(conv_id, task_id)

    async def quiet_workflow_chat(task_id: str, role: str, content: str):
        await asyncio.sleep(0.05)
        context = routes.workflow_engine.get_workflow(task_id)
        assert context is not None
        context.add_message(role, content)
        context.add_message("assistant", f"已同步到工作流：{content}")
        return {
            "role": "assistant",
            "content": f"已同步到工作流：{content}",
            "phase": context.current_phase.value,
        }

    monkeypatch.setattr(routes.workflow_engine, "add_chat_message", quiet_workflow_chat)
    monkeypatch.setattr(routes, "CONVERSATION_STREAM_HEARTBEAT_SECONDS", 0.01, raising=False)

    with client.stream(
        "POST",
        f"{api_prefix}/conversations/{conv_id}/chat/stream",
        json={"content": "补充遮挡画面删除策略"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200, body
    assert "event: heartbeat" in body
    assert "已同步到工作流：补充遮挡画面删除策略" in body


def test_linked_conversation_upload_syncs_file_to_workflow(client, api_prefix):
    conv_id = "conv-linked-upload"
    task_id = "task-linked-upload"
    _linked_conversation(conv_id, task_id)

    response = client.post(
        f"{api_prefix}/conversations/{conv_id}/upload",
        files={"file": ("disclosure.txt", b"supplemental disclosure text", "text/plain")},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["filename"] == "disclosure.txt"
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    assert any(m["role"] == "user" and m["content"] == "supplemental disclosure text" for m in context.message_history)
    assert routes.conversations_store[conv_id]["messages"][0]["type"] == "file"


def test_create_workflow_from_conversation_forwards_engine_callbacks(client, api_prefix, monkeypatch):
    conv_id = "conv-create-workflow-callbacks"
    now = datetime.now().isoformat()
    routes.conversations_store[conv_id] = {
        "id": conv_id,
        "title": "Create workflow callbacks",
        "messages": [
            {
                "id": "user-message",
                "role": "user",
                "content": "一种可调屏幕角度的沉浸式 Cave 视频处理系统",
                "timestamp": now,
                "type": "text",
            }
        ],
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "linked_workflow_id": None,
    }

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        assert phase_callback is not None
        assert event_callback is not None
        event_callback(
            "专利撰写 Agent",
            "agent.thinking",
            "🧾 正在生成权利要求书...",
            {"agent_name": "专利撰写 Agent", "thought": "生成权利要求书", "step": 1},
        )
        context.current_phase = routes.EngineWorkflowState.COMPLETED
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(
        f"{api_prefix}/conversations/{conv_id}/create-workflow",
        json={"user_id": "test_user", "target_country": "中国"},
    )

    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    assert any(
        event.event_type == "agent.thinking"
        and event.agent == "专利撰写 Agent"
        and "正在生成权利要求书" in event.message
        for event in routes.task_events[task_id]
    )



def test_restart_failed_linked_workflow_uses_engine_initialized_state(client, api_prefix, monkeypatch):
    conv_id = "conv-restart-workflow"
    task_id = "task-restart-workflow"
    _linked_conversation(conv_id, task_id)
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    context.requirement_analysis = {"tech_field": "old"}

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/restart")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "restarted"
    assert context.requirement_analysis == {}
    assert context.current_phase.value == "initialized"


def test_restart_failed_linked_workflow_restores_uploaded_disclosure(client, api_prefix, monkeypatch):
    conv_id = "conv-restart-upload"
    task_id = "task-restart-upload"
    _linked_conversation(conv_id, task_id)
    disclosure = "uploaded disclosure text with adjustable immersive cave display screens"
    routes.conversations_store[conv_id]["messages"].append(
        {
            "id": "file-msg",
            "role": "user",
            "content": disclosure,
            "timestamp": datetime.now().isoformat(),
            "type": "file",
            "metadata": {"filename": "disclosure.txt"},
        }
    )
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    context.original_description = ""
    context.add_message("user", "short title only")

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/restart")

    assert response.status_code == 200, response.text
    assert context.original_description == disclosure


def test_start_linked_workflow_restores_uploaded_disclosure(client, api_prefix, monkeypatch):
    conv_id = "conv-start-upload"
    task_id = "task-start-upload"
    _linked_conversation(conv_id, task_id)
    disclosure = "uploaded disclosure text for Cave folded-screen video processing"
    routes.conversations_store[conv_id]["messages"].append(
        {
            "id": "file-msg",
            "role": "user",
            "content": disclosure,
            "timestamp": datetime.now().isoformat(),
            "type": "file",
            "metadata": {"filename": "disclosure.txt"},
        }
    )
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    context.original_description = ""

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/start")

    assert response.status_code == 200, response.text
    assert context.original_description == disclosure


def test_start_workflow_persists_workflow_snapshot_after_phase_callback(
    client, api_prefix, monkeypatch
):
    conv_id = "conv-start-phase-persist"
    task_id = "task-start-phase-persist"
    _linked_conversation(conv_id, task_id)
    saved_workflows = []

    class FakeStore:
        async def save(self, category, key, value):
            if category == "workflows" and key == task_id:
                saved_workflows.append(value)

    monkeypatch.setattr(routes, "_get_persist_store", lambda: FakeStore())

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        context.current_phase = routes.EngineWorkflowState.REQUIREMENT_ANALYSIS
        context.requirement_analysis = {"tech_field": "Cave folded-screen video"}
        if phase_callback:
            await phase_callback(
                routes.EngineWorkflowState.REQUIREMENT_ANALYSIS,
                PhaseResult(
                    phase=WorkflowPhase.REQUIREMENT,
                    success=True,
                    duration_seconds=0,
                    output=context.requirement_analysis,
                ),
            )
        assert any(
            snapshot.get("current_state") == "requirement_analysis"
            and snapshot.get("outputs", {})
            .get("requirement_analysis", {})
            .get("tech_field")
            == "Cave folded-screen video"
            for snapshot in saved_workflows
        )
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/start")

    assert response.status_code == 200, response.text


def test_restart_linked_workflow_prefers_uploaded_disclosure_over_placeholder(
    client, api_prefix, monkeypatch
):
    conv_id = "conv-restart-placeholder-upload"
    task_id = "task-restart-placeholder-upload"
    _linked_conversation(conv_id, task_id)
    disclosure = "Cave folded-screen disclosure with adjustable immersive display content"
    routes.conversations_store[conv_id]["messages"].append(
        {
            "id": "file-msg",
            "role": "user",
            "content": disclosure,
            "timestamp": datetime.now().isoformat(),
            "type": "file",
            "metadata": {"filename": "disclosure.txt"},
        }
    )
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None
    context.original_description = "任(00:00:00): 这样我开个头！这个东西"

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/restart")

    assert response.status_code == 200, response.text
    assert context.original_description == disclosure


def test_restart_workflow_preserves_failed_engine_result(client, api_prefix, monkeypatch):
    conv_id = "conv-restart-engine-failed"
    task_id = "task-restart-engine-failed"
    _linked_conversation(conv_id, task_id)
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        context.current_phase = routes.EngineWorkflowState.FAILED
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/restart")

    assert response.status_code == 200, response.text
    assert context.current_phase == routes.EngineWorkflowState.FAILED
    assert all(
        event.event_type != "workflow.completed"
        for event in routes.task_events[task_id]
    )
    assert any(
        event.event_type == "workflow.failed"
        for event in routes.task_events[task_id]
    )


def test_start_workflow_preserves_failed_engine_result(client, api_prefix, monkeypatch):
    conv_id = "conv-start-engine-failed"
    task_id = "task-start-engine-failed"
    _linked_conversation(conv_id, task_id)
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None

    async def fake_execute_full_workflow(context, phase_callback=None, event_callback=None):
        context.current_phase = routes.EngineWorkflowState.FAILED
        return context

    monkeypatch.setattr(routes.workflow_engine, "execute_full_workflow", fake_execute_full_workflow)

    response = client.post(f"{api_prefix}/workflows/{task_id}/start")

    assert response.status_code == 200, response.text
    assert context.current_phase == routes.EngineWorkflowState.FAILED
    assert all(
        event.event_type != "workflow.completed"
        for event in routes.task_events[task_id]
    )
    assert any(
        event.event_type == "workflow.failed"
        for event in routes.task_events[task_id]
    )


def test_workflow_docx_export_serves_authored_docx_path(client, api_prefix, tmp_path):
    conv_id = "conv-export-authored-docx"
    task_id = "task-export-authored-docx"
    _linked_conversation(conv_id, task_id)
    context = routes.workflow_engine.get_workflow(task_id)
    assert context is not None

    authored_docx = tmp_path / "authored.docx"
    authored_docx.write_bytes(b"authored-docx-bytes")
    context.patent_draft = {
        "docx_path": str(authored_docx),
        "claims": {"independent_claim": "wrong regenerated claim", "dependent_claims": []},
        "description": {},
        "abstract": "wrong regenerated abstract",
    }

    response = client.get(f"{api_prefix}/workflows/{task_id}/export/docx")

    assert response.status_code == 200, response.text
    assert response.content == b"authored-docx-bytes"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
