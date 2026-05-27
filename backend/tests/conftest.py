from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router as api_router
from src.core import settings

# ── Test App ──────────────────────────────────────────────────────────────────
# Create a minimal FastAPI application with API routes only.
# Startup/shutdown events (container init, Redis) are NOT registered.
# Route-level singletons (tasks_store, workflow_engine, profiles) are
# initialised when routes.py is imported above.
test_app = FastAPI(title="Patent-Agents Test")
test_app.include_router(api_router, prefix=settings.api_version)


# Add root-level endpoints for comprehensive health checks
@test_app.get("/")
async def _test_root():
    return {
        "name": "专利智脑 - AI驱动的专利申请多智能体系统",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.environment.value,
        "api_base": settings.api_version,
    }


@test_app.get("/health")
async def _test_health():
    return {
        "status": "healthy",
        "environment": settings.environment.value,
    }


# ── Pytest Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_llm_api_key(monkeypatch: pytest.MonkeyPatch):
    """Clear the LLM API key during tests so _call_hermes uses mock responses.

    Without this the background agent tasks (CEOAgent → HermesCore.execute)
    make real LLM API calls that hang or time out in TestClient context.
    """
    monkeypatch.setattr(settings.llm, "openai_api_key", "")


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient bound to the test app (no startup/shutdown events)."""
    with TestClient(test_app) as client:
        yield client


@pytest.fixture
def api_prefix() -> str:
    """URL prefix for all API routes, e.g. ``/api/v1``."""
    return settings.api_version
