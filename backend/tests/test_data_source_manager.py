import asyncio

import pytest

from src.data_sources.base import DataSource, DataSourceManager
from src.models.domain import DataSourceConfig, PriorArtReference, SearchQuery


class _SlowSource(DataSource):
    async def search(self, query: SearchQuery):
        await asyncio.sleep(1)
        return []

    async def get_details(self, reference_id: str):
        return None


class _FastSource(DataSource):
    async def search(self, query: SearchQuery):
        return [
            PriorArtReference(
                reference_id="FAST-1",
                title="Fast evidence",
                abstract="A verified reference.",
                source=self.config.source_id,
                similarity_score=0.8,
            )
        ]

    async def get_details(self, reference_id: str):
        return None


@pytest.mark.asyncio
async def test_search_all_skips_timed_out_source_without_blocking_others(monkeypatch):
    manager = DataSourceManager()
    manager.sources = {
        "slow": _SlowSource(
            DataSourceConfig(
                source_id="slow",
                name="Slow Source",
                source_type="patent",
                base_url="https://example.invalid",
                enabled=True,
            )
        ),
        "fast": _FastSource(
            DataSourceConfig(
                source_id="fast",
                name="Fast Source",
                source_type="patent",
                base_url="https://example.invalid",
                enabled=True,
            )
        ),
    }
    monkeypatch.setattr(manager, "SOURCE_SEARCH_TIMEOUT_SECONDS", 0.01)

    results = await manager.search_all(
        SearchQuery(query="screen posture adaptation", databases=["slow", "fast"])
    )

    assert [item.reference_id for item in results] == ["FAST-1"]
    assert manager.last_search_status["fast"]["success"] is True
    assert manager.last_search_status["slow"]["success"] is False
    assert "超过" in manager.last_search_status["slow"]["error"]
