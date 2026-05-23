from __future__ import annotations

"""
Task CRUD endpoint tests.
"""

import uuid

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _valid_task_payload(**overrides) -> dict:
    """Return a minimal valid task creation payload."""
    payload = {
        "tech_description": "A novel AI-powered patent analysis system that leverages ",
        "user_id": "test_user_001",
    }
    payload.update(overrides)
    return payload


def _create_task(client, api_prefix, **overrides) -> dict:
    """Create a task and return the JSON response body."""
    response = client.post(f"{api_prefix}/tasks", json=_valid_task_payload(**overrides))
    assert response.status_code == 201, f"Task creation failed: {response.text}"
    return response.json()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestCreateTask:
    def test_create_minimal(self, client, api_prefix):
        task = _create_task(client, api_prefix)
        assert "task_id" in task
        assert task.get("current_state") is not None
        assert task.get("created_at") is not None

    def test_create_with_all_fields(self, client, api_prefix):
        task = _create_task(
            client,
            api_prefix,
            tech_description="Advanced quantum computing algorithm for optimizing supply chain logistics and resource allocation across distributed systems.",
            patent_type_preference="invention",
            user_id="test_user_001",
        )
        assert task.get("user_id") == "test_user_001"

    def test_create_missing_required_field_returns_422(self, client, api_prefix):
        response = client.post(f"{api_prefix}/tasks", json={})
        assert response.status_code == 422
        errors = response.json().get("detail", [])
        assert any("tech_description" in str(e) for e in errors)


class TestListTasks:
    def test_list_returns_tasks(self, client, api_prefix):
        # Create at least one task first
        _create_task(client, api_prefix, tech_description="A novel AI-powered patent analysis system for automated prior art search and document generation tasks.")

        response = client.get(f"{api_prefix}/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) >= 1

    def test_list_no_tasks(self, client, api_prefix):
        # The in-memory store is shared across tests, so this just verifies shape
        response = client.get(f"{api_prefix}/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)


class TestGetTask:
    def test_get_task_by_id(self, client, api_prefix):
        created = _create_task(client, api_prefix, tech_description="A novel AI-powered patent analysis system for automated document classification and prior art search.")

        response = client.get(f"{api_prefix}/tasks/{created['task_id']}")
        assert response.status_code == 200
        task = response.json()
        assert task["task_id"] == created["task_id"]

    def test_get_nonexistent_task_returns_404(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.get(f"{api_prefix}/tasks/{fake_id}")
        assert response.status_code == 404
        assert "detail" in response.json()


class TestCancelTask:
    def test_cancel_existing_task(self, client, api_prefix):
        created = _create_task(client, api_prefix, tech_description="A novel AI-powered patent analysis system for automated image recognition and classification.")

        response = client.post(f"{api_prefix}/tasks/{created['task_id']}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        assert "message" in data

    def test_cancel_nonexistent_task_returns_404(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.post(f"{api_prefix}/tasks/{fake_id}/cancel")
        assert response.status_code == 404
        assert "detail" in response.json()
