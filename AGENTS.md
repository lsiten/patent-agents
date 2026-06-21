# 专利智脑 — Project Map

## Identity

AI-driven patent application multi-agent system. It converts invention disclosures and technical conversations into patent application DOCX files through Hermes Agent collaboration, LangGraph workflow routing, and AG-UI-compatible realtime events.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, LangGraph, OpenAI SDK-compatible clients, hermes-agent `run_agent.AIAgent`
- **Frontend**: Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, `@ag-ui/core`, `@ag-ui/client`
- **Runtime**: uvicorn, npm, optional Redis/Celery, local dev/test/production isolation through `start.sh`

## Architecture

```text
User
  ←→ Next.js Frontend
  ←→ FastAPI REST + SSE
  ←→ AG-UI event adapter / WorkflowProtocolStore
  ←→ LangGraph StateGraph workflow runtime
  ←→ Hermes Agent team
       ├── CEO Agent: orchestration and shared facts only
       ├── Brainstorm Partner
       ├── Requirement Analyst
       ├── Retrieval Analyst
       ├── Patent Writer
       └── Quality Reviewer
```

## Workflow

Formal patent generation must not start directly from a prompt or uploaded file. The expected flow is:

```text
brainstorm
→ title_generation
→ human_confirm_start
→ requirement_analysis
→ requirement_gate
→ retrieval
→ retrieval_gate
→ writing
→ writing_gate
→ quality_review
→ quality_gate
→ final_docx
```

Quality failures route back to the responsible Agent. Each round appends to `phase_rounds`; accepted facts merge into `shared_facts`.

## Directory Structure

```text
backend/
  main.py
  hermes_home/profiles/          Hermes Agent profiles, SOUL.md, skills
  src/
    api/                         REST/SSE route modules
    agents/                      Agent config, Hermes adapters, tools
    core/
      constants/                 environment, patent rules, workflow thresholds
      llm/
        client.py                unified LLM service
        providers/               built-in text/image provider catalog
      workflow/                  LangGraph runtime, nodes, contracts, gates, checkpoints, events
      patent/                    deterministic patent compliance checks
      config.py                  settings and runtime reload
    data_sources/                patent/paper/web/authority connectors
    document_gen/                DOCX and drawing generation
    models/                      ORM/Pydantic models
    repositories/                persistence layer
    services/                    domain services

frontend/
  app/                           Next.js routes
  components/chat/               chat workspace, composer, workflow strip
  components/workflow/           workflow page, output renderers, round tabs, logs
  lib/api/                       REST/SSE client
  lib/constants/                 frontend runtime constants
  lib/workflowProtocolStore.ts   AG-UI event reducer
```

## Entry Points

| Layer | File | Role |
| --- | --- | --- |
| Backend | `backend/main.py` | FastAPI app creation and middleware |
| API | `backend/src/api/routers/` | Domain route modules |
| Workflow | `backend/src/core/workflow/` | LangGraph runtime and workflow modules |
| Compatibility | `backend/src/core/workflow_engine.py` | Thin legacy facade only |
| Agents | `backend/src/agents/agent_config.py` | Hermes profile loader and `AIAgent` factory |
| LLM Providers | `backend/src/core/llm/providers/catalog.py` | Built-in provider metadata |
| Frontend | `frontend/app/layout.tsx` | Root layout |
| Chat | `frontend/components/chat/ChatWorkspace.tsx` | Main conversation UI |
| Workflow UI | `frontend/components/workflow/WorkflowTaskPage.tsx` | Workflow detail page |

## Constants And Provider Policy

- Backend constants belong in `backend/src/core/constants/`.
- Frontend runtime constants belong in `frontend/lib/constants/runtime.ts`.
- Built-in LLM/image provider metadata belongs in `backend/src/core/llm/providers/`.
- Do not hardcode API keys, case-specific terms, mock content, or patent examples as universal rules.
- Provider catalog may contain default base URLs, model IDs, categories, and environment variable names only.

## Quality Gates

- Patent output must satisfy `专利申请文件撰写完整规范手册.md`.
- Independent claim 1 must use exactly 3 or 4 steps.
- Every semicolon and period in claims must be followed by a newline.
- Transcript timestamps, filenames, markdown artifacts, and disclosure formatting noise must not leak into DOCX.
- Drawing numbers, titles, body references, generated files, and DOCX insertions must match.
- Patent database sources are enabled only when configured. If patent sources have no usable evidence, search papers, public web pages, and authoritative sites before asking the user for more information.

## Development

```bash
./start.sh dev         # frontend :3000, backend :8000
./start.sh test        # frontend :3100, backend :8100
./start.sh production  # frontend :10001, backend :10002
```

Run checks:

```bash
cd backend && PYTHONPATH=. python -m pytest
cd frontend && npm run typecheck
bash scripts/test_start_sh_isolation.sh
```

Browser acceptance must use real browser interaction, not direct API calls.
