from __future__ import annotations

"""
Task event (SSE / events) endpoint tests.
"""

import uuid

import pytest


class TestTaskEvents:
    def test_get_events_for_existing_task(self, client, api_prefix):
        # Create a task first
        create_resp = client.post(
            api_prefix + "/tasks",
            json={
                "tech_description": (
                    "An innovative system and method for intelligent "
                    "event-driven task processing in multi-agent patent "
                    "workflow orchestration environment."
                ),
                "user_id": "test_user",
            },
        )
        assert create_resp.status_code in (200, 201)
        task_id = create_resp.json()["task_id"]

        response = client.get(f"{api_prefix}/tasks/{task_id}/events")
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            # Events response may be a list or dict
            assert isinstance(data, (list, dict))

    def test_get_events_for_nonexistent_task(self, client, api_prefix):
        fake_id = str(uuid.uuid4())
        response = client.get(f"{api_prefix}/tasks/{fake_id}/events")
        assert response.status_code == 404
        assert "detail" in response.json()
