from __future__ import annotations

"""
Chat endpoint tests.
"""

import pytest


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
