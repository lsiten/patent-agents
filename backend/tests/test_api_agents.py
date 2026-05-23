from __future__ import annotations

"""
Agent management endpoint tests.
"""

import pytest


CEO_PROFILE_ID = "patent.ceo.v1"
WRITER_PROFILE_ID = "patent.writer.v1"


class TestListAgents:
    def test_list_returns_all_profiles(self, client, api_prefix):
        response = client.get(f"{api_prefix}/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        agents = data["agents"]
        assert len(agents) >= 5  # CEO + 4 specialist roles

        # Verify CEO agent exists and is enabled by default
        ceo = next((a for a in agents if a["id"] == CEO_PROFILE_ID), None)
        assert ceo is not None, "CEO agent not found"
        assert ceo["enabled"] is True

    def test_list_has_required_fields(self, client, api_prefix):
        response = client.get(f"{api_prefix}/agents")
        agents = response.json()["agents"]
        for agent in agents:
            assert "id" in agent
            assert "name" in agent
            assert "enabled" in agent
            assert isinstance(agent["enabled"], bool)
            assert "description" in agent
            assert "role" in agent


class TestAgentDetail:
    def test_get_ceo_detail(self, client, api_prefix):
        response = client.get(f"{api_prefix}/agents/{CEO_PROFILE_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["id"] == CEO_PROFILE_ID
        assert "tools" in data
        assert isinstance(data.get("tools"), list)

    def test_get_writer_detail(self, client, api_prefix):
        response = client.get(f"{api_prefix}/agents/{WRITER_PROFILE_ID}")
        assert response.status_code == 200
        assert response.json()["config"]["id"] == WRITER_PROFILE_ID

    def test_get_nonexistent_agent_returns_404(self, client, api_prefix):
        response = client.get(f"{api_prefix}/agents/nonexistent_agent_xyz")
        assert response.status_code == 404
        assert "detail" in response.json()


class TestToggleAgent:
    def test_toggle_agent_tool_changes_state(self, client, api_prefix):
        # Get list of tools for CEO agent
        detail = client.get(f"{api_prefix}/agents/{CEO_PROFILE_ID}").json()
        tools = detail.get("tools", [])
        assert len(tools) > 0
        tool_id = tools[0]["id"]

        # Toggle the tool off
        response = client.post(
            f"{api_prefix}/agents/{CEO_PROFILE_ID}/tools/{tool_id}/toggle",
            params={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # Toggle back on
        response = client.post(
            f"{api_prefix}/agents/{CEO_PROFILE_ID}/tools/{tool_id}/toggle",
            params={"enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_toggle_nonexistent_agent_returns_404(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/agents/nonexistent_xyz/tools/search/toggle",
            params={"enabled": False},
        )
        assert response.status_code == 404
        assert "detail" in response.json()
