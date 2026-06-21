## backend/src/ — Module Map

### Structure

```text
src/
├── api/             REST/SSE routes by domain
├── agents/          Hermes Agent configuration, adapters, tools
├── core/            config, constants, LLM, workflow runtime, events, tasks
├── data/            local application data helpers
├── data_sources/    external patent/paper/web/authority connectors
├── document_gen/    DOCX, drawing, template generation
├── infrastructure/  integration and runtime infrastructure helpers
├── knowledge/       retrieval and knowledge-base helpers
├── models/          ORM and Pydantic models
├── repositories/    persistence access
├── services/        business services
└── utils/           narrow utility helpers
```

### Dependency Direction

```text
api → services → repositories/models
api → core/workflow → agents → hermes tools
core/config/constants/llm are foundation modules
data_sources/document_gen/knowledge are called through services, workflow nodes, or Hermes tools
```

Keep cross-module imports intentional. Avoid introducing new monolithic files; workflow code belongs under `core/workflow/`, route code under `api/routers/`, provider metadata under `core/llm/providers/`, and constants under `core/constants/`.

### Key Patterns

- Hermes `run_agent.AIAgent` remains the professional Agent execution base.
- LangGraph `StateGraph` owns patent workflow routing and recovery.
- AG-UI-compatible events flow from workflow/agent/tool execution to frontend SSE reducers.
- All accepted phase facts merge into shared workflow facts; temporary round output must not overwrite history.
- No mock content, no case-specific fallback logic, and no hardcoded patent examples as generic rules.
