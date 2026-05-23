from __future__ import annotations

"""
Health-check & root-endpoint tests.
"""

import pytest


class TestRootEndpoint:
    def test_root_returns_system_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "name" in data
        assert "version" in data
        assert "api_base" in data

    def test_root_includes_api_base(self, client, api_prefix):
        response = client.get("/")
        assert response.json()["api_base"] == api_prefix


class TestHealthEndpoint:
    def test_health_check_returns_healthy(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data


class TestOpenAPI:
    def test_openapi_schema_available(self, client):
        """Verify that the OpenAPI schema is generated with all paths."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert len(schema["paths"]) > 5  # core endpoints present
        # Verify some expected path patterns
        paths = schema["paths"]
        agent_paths = [p for p in paths if "/agents" in p and "{" not in p]
        assert any("/agents" in p for p in paths)
        assert any("/tasks" in p for p in paths)
        assert any("/system/status" in p for p in paths)

    def test_redoc_schema_available(self, client):
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_docs_ui_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
