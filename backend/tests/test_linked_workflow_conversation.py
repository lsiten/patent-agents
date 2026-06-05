from __future__ import annotations

from datetime import datetime
import json

import pytest

from src.api import routes


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
