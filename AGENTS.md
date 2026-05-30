# 专利智脑 — Project Map

## Identity
AI-driven patent application multi-agent system. Converts technical inventions into professional patent filings via coordinated AI agents.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI 0.109, SQLAlchemy 2.0, Celery, Redis, LangChain, OpenAI SDK
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS
- **Infrastructure**: Poetry (Python deps), npm (frontend deps), uvicorn, docker-ready

## Architecture (Two-Layer)
```
User ←→ Next.js Frontend ←→ FastAPI REST API + SSE ←→ Agent System
                                                          ├── CEO Agent (orchestrator)
                                                          ├── Requirement Analyst
                                                          ├── Retrieval Analyst
                                                          ├── Patent Writer
                                                          ├── Quality Reviewer
                                                          └── Brainstorm Partner
```
Agents run on `hermes-agent` package (`run_agent.AIAgent`), with configuration in `backend/hermes_home/profiles/`. Workflow engine (`core/workflow_engine.py`) manages multi-step patent drafting pipelines.

## Directory Structure
```
.
├── AGENTS.md                  ← THIS FILE
├── backend/                   → Python FastAPI backend
│   ├── src/                   → Application source
│   │   ├── api/               →   REST routes + auth
│   │   ├── agents/            →   Multi-agent system + Hermes framework
│   │   ├── core/              →   Config, DI, events, tasks, middleware
│   │   ├── models/            →   DB models (SQLAlchemy + Pydantic)
│   │   ├── data_sources/      →   External data connectors (patent DBs, web)
│   │   ├── document_gen/      →   Patent document templates + generation
│   │   ├── knowledge/         →   Knowledge base + retrieval
│   │   ├── prompts/           →   LLM prompt templates
│   │   └── tools/             →   Agent tool definitions
│   └── tests/                 →  (minimal, see tests/AGENTS.md)
├── frontend/                  → Next.js 14 frontend
│   ├── app/                   →   App Router pages (9 routes)
│   ├── components/            →   React components (ui/, layout/, workflow/)
│   └── styles/                →   Global CSS + animations
├── docs/                      → Design docs, API specs, DB schemas
├── scripts/                   → Utility scripts
├── DESIGN.md                  → MongoDB design reference (legacy)
└── PROJECT_SUMMARY.md         → v1.0 status summary
```

## Entry Points
| Layer | File | Role |
|-------|------|------|
| Backend | `backend/main.py` | uvicorn app launch, middleware registration |
| Backend | `backend/src/api/routes.py` | All REST endpoints (934 lines) |
| Frontend | `frontend/app/layout.tsx` | Root layout with Navbar |
| Frontend | `frontend/app/page.tsx` | Landing page |
| Agents | `backend/src/agents/agent_config.py` | Agent config loader + AIAgent factory |
| Workflow | `backend/src/core/workflow_engine.py` | Patent workflow orchestration (917 lines) |

## Key Conventions
- **API**: FastAPI REST + SSE streaming for real-time agent thinking updates
- **Auth**: JWT via python-jose, middleware in `core/middleware.py`
- **DI**: dependency-injector library, container in `core/container.py`
- **Events**: InMemoryEventBus / RedisEventBus in `core/events.py`
- **Config**: pydantic-settings via `Settings` class in `core/config.py`
- **Tasks**: Celery for sync tasks, LocalTaskExecutor for dev/fallback
- **DB**: SQLAlchemy async with aiosqlite (dev) / asyncpg (prod)
- **Agents**: AIAgent (hermes-agent) → YAML config + SOUL.md → patent tools

## Critical Files (>500 lines)
- `backend/src/api/routes.py` (934) — All REST endpoints
- `backend/src/core/workflow_engine.py` (917) — Workflow DAG executor
- `backend/src/agents/agent_config.py` — Agent config loader + AIAgent factory
- `backend/hermes_home/profiles/` — 6 agent profiles (YAML + SOUL.md)
- `frontend/app/agents/page.tsx` (880) — Agent interaction UI
- `frontend/app/agent-selector/page.tsx` (744) — Agent selection page

## Development Setup
```bash
./start.sh backend   # Python venv + uvicorn on :8000
./start.sh frontend  # npm install + next dev on :3000
```

## Quality Gates
- Format: black (line-length 100), isort
- Lint: flake8, mypy (partial typing)
- Test: pytest + pytest-asyncio (target 70% cov), test dir at `backend/tests/`
- No CI/CD config found — assume manual/adhoc deploy
