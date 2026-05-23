from __future__ import annotations

"""
Workflow session endpoint tests.
"""

import uuid

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_task(client, api_prefix, desc: str = "Workflow test task description for patent analysis system.") -> str:
    """Create a task and return its task_id."""
    resp = client.post(
        f"{api_prefix}/tasks",
        json={"tech_description": desc, "user_id": "test_user"},
    )
    assert resp.status_code == 201, f"Task setup failed: {resp.text}"
    return resp.json()["task_id"]


# ── Tests ────────────────────────────────────────────────────────────────────


class TestCreateWorkflow:
    def test_create_session_with_valid_task(self, client, api_prefix):
        task_id = _create_task(client, api_prefix)

        response = client.post(
            f"{api_prefix}/workflows",
            json={
                "task_id": task_id,
                "tech_description": "A novel AI-powered patent analysis system for automated classification.",
                "user_id": "test_user",
            },
        )
        # Returns 201 on creation
        assert response.status_code == 201, f"Workflow creation failed: {response.text}"
        data = response.json()
        assert "task_id" in data
        assert data["task_id"] == task_id

    def test_create_session_with_nonexistent_task(self, client, api_prefix):
        # Workflow engine creates new sessions regardless of existing tasks
        response = client.post(
            f"{api_prefix}/workflows",
            json={
                "task_id": str(uuid.uuid4()),
                "tech_description": "A novel AI-powered patent analysis system for automated classification.",
                "user_id": "test_user",
            },
        )
        # Workflow accepts any task_id
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data

    def test_create_session_missing_tech_description(self, client, api_prefix):
        response = client.post(f"{api_prefix}/workflows", json={})
        assert response.status_code == 422
        errors = response.json().get("detail", [])
        assert any("tech_description" in str(e) for e in errors)


class TestListWorkflows:
    def test_list_sessions(self, client, api_prefix):
        response = client.get(f"{api_prefix}/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestGetWorkflow:
    def test_get_existing_session(self, client, api_prefix):
        task_id = _create_task(client, api_prefix)
        create_resp = client.post(
            f"{api_prefix}/workflows",
            json={
                "task_id": task_id,
                "tech_description": "A novel AI-powered patent analysis system for automated classification.",
                "user_id": "test_user",
            },
        )
        data = create_resp.json()

        response = client.get(f"{api_prefix}/workflows/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id

    def test_get_nonexistent_session(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.get(f"{api_prefix}/workflows/{fake_id}")
        assert response.status_code == 404
        assert "detail" in response.json()


class TestWorkflowPhases:
    def test_get_phases_for_existing_session(self, client, api_prefix):
        task_id = _create_task(client, api_prefix)
        client.post(
            f"{api_prefix}/workflows",
            json={
                "task_id": task_id,
                "tech_description": "A novel AI-powered patent analysis system for automated classification.",
                "user_id": "test_user",
            },
        )

        response = client.get(f"{api_prefix}/workflows/{task_id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "count" in data

    def test_get_phases_nonexistent_session(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.get(f"{api_prefix}/workflows/{fake_id}/messages")
        assert response.status_code == 404


class TestDeleteWorkflow:
    def test_delete_existing_session(self, client, api_prefix):
        task_id = _create_task(client, api_prefix)
        client.post(
            f"{api_prefix}/workflows",
            json={
                "task_id": task_id,
                "tech_description": "A novel AI-powered patent analysis system for automated classification.",
                "user_id": "test_user",
            },
        )

        response = client.post(f"{api_prefix}/workflows/{task_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "cancelled"

        # Verify it's gone
        get_resp = client.get(f"{api_prefix}/workflows/{task_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_session(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.post(f"{api_prefix}/workflows/{fake_id}/cancel")
        assert response.status_code == 404
        assert "detail" in response.json()
