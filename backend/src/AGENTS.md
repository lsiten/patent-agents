## backend/src/ — Module Map

### Structure (9 modules)
```
src/
├── api/          → REST routes, request/response models, auth
├── agents/       → Multi-agent system (Hermes framework, profiles, service)
├── core/         → Foundation: config, DI, events, tasks, middleware, exceptions
├── models/       → SQLAlchemy ORM models + Pydantic schemas
├── data_sources/ → External patent DB connectors, web scraping
├── document_gen/ → Patent doc templates (DOCX/PDF), LaTeX generation
├── knowledge/    → Vector store, retrieval, knowledge base
├── prompts/      → Prompt templates for each agent role
└── tools/        → Agent tool definitions (search, db, web)
```

### Dependency Direction
```
api ← core ← agents ← (hermes, profiles, service)
                    ↘ tools, prompts, knowledge, data_sources, document_gen
```
**core** has zero internal deps — everything depends on it.

### Key Patterns
- **DI**: `core/container.py` wires all modules via dependency-injector
- **Config**: `core/config.py` is singleton settings object used everywhere
- **Events**: SSE streams flow from agents → core/events.py → API → frontend
- **Tasks**: Long workflows in `core/workflow_engine.py` orchestrate agents

### File Distribution
| Module | Files | Lines | Critical File |
|--------|-------|-------|---------------|
| agents | 13 | ~4,500 | `profiles/default_profiles.py` (826) |
| core | 11 | ~2,500 | `workflow_engine.py` (917) |
| api | 2 | ~1,000 | `routes.py` (934) |
| models | 2 | <200 | — |
| others | 12 | ~1,000 | — |
