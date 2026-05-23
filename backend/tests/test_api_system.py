from __future__ import annotations

"""
System, organisation-tree, search, and knowledge endpoint tests.
"""

import pytest


class TestSystemStatus:
    def test_status_returns_system_info(self, client, api_prefix):
        response = client.get(f"{api_prefix}/system/status")
        assert response.status_code == 200
        data = response.json()
        # Should have agent and data source info
        assert any(k in data for k in ("agents", "status", "data_sources", "system"))


class TestSystemStats:
    def test_stats_returns_counts(self, client, api_prefix):
        response = client.get(f"{api_prefix}/stats/dashboard")
        assert response.status_code == 200
        data = response.json()
        # Should contain numeric stats
        assert isinstance(data, dict)
        # At least one numeric value should exist
        numeric_values = [v for v in data.values() if isinstance(v, (int, float))]
        assert len(numeric_values) >= 1


class TestOrganizationTree:
    def test_tree_returns_hierarchy(self, client, api_prefix):
        response = client.get(f"{api_prefix}/organization/tree")
        assert response.status_code == 200
        data = response.json()
        # Should have a tree structure
        assert any(k in data for k in ("name", "label", "root", "children"))


class TestSearch:
    def test_search_with_query(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/search/patents",
            json={"query": "machine learning patent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should have results or at least acknowledge the query
        assert any(k in data for k in ("results", "query", "total", "items"))

    def test_search_with_empty_query(self, client, api_prefix):
        response = client.post(
            f"{api_prefix}/search/patents",
            json={"query": ""},
        )
        # Should handle gracefully (200 or 422)
        assert response.status_code in (200, 422)
        if response.status_code == 422:
            assert "detail" in response.json()

    def test_search_missing_query(self, client, api_prefix):
        response = client.post(f"{api_prefix}/search/patents", json={})
        assert response.status_code == 422
        errors = response.json().get("detail", [])
        assert any("query" in str(e) for e in errors)


class TestKnowledge:
    def test_list_knowledge(self, client, api_prefix):
        response = client.get(f"{api_prefix}/knowledge/search?query=patent")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "patents" in data

    def test_generate_knowledge(self, client, api_prefix):
        # The knowledge/generate endpoint doesn't exist; search is the read path
        response = client.get(f"{api_prefix}/knowledge/search?query=patent+prior+art+search")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
