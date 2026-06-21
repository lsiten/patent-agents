## core/ — Foundation And Workflow Runtime

### Modules

| Path | Responsibility |
| --- | --- |
| `config.py` | pydantic-settings application configuration and runtime reload |
| `constants/` | environment names, patent hard rules, workflow thresholds/timeouts |
| `llm/client.py` | unified LLM client/service and provider-specific client creation |
| `llm/providers/` | built-in text LLM and image generation provider catalog |
| `workflow/` | LangGraph workflow runtime, nodes, contracts, gates, checkpoints, events, artifacts |
| `workflow_engine.py` | thin compatibility facade for legacy imports only |
| `patent/` | deterministic patent compliance helpers |
| `events.py` | event bus abstractions |
| `tasks.py` | background task executors |
| `middleware.py` | request/SSE middleware |
| `security/` | secret encryption helpers |

### Rules

- Add new cross-cutting constants to `constants/`, not inline inside workflow/API/frontend code.
- Add new LLM or image providers to `llm/providers/catalog.py`, not directly inside `config.py` or UI code.
- Do not put professional patent judgments in deterministic helpers. Local checks are for hard rules only.
- Do not expand `workflow_engine.py`; move workflow behavior into `workflow/` modules.
- Runtime config reload must reset cached LLM clients so changed provider settings take effect immediately.

### Workflow Ownership

LangGraph owns:

- node sequence
- quality gate routing
- user interrupts
- route history
- phase round persistence
- shared facts merging

Hermes Agents own:

- professional analysis
- retrieval reasoning
- patent drafting
- quality review
- tool/skill use

CEO owns only orchestration, routing, and shared context maintenance.
