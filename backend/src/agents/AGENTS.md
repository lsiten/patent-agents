## agents/ — Multi-Agent System

### Layers
```
agent_service.py        ← Orchestration layer (662 lines)
  profiles/             ← Agent personality definitions (826 lines)
    default_profiles.py
  hermes/               ← Custom agent framework (719+ lines)
```

### Agent Roles (6 profiles in `profiles/default_profiles.py`)
| Agent | Role |
|-------|------|
| CEO | Workflow orchestrator, delegates tasks |
| Requirement Analyst | Extracts patent requirements from invention descriptions |
| Retrieval Analyst | Searches prior art, patent databases |
| Patent Writer | Drafts patent specifications, claims |
| Quality Reviewer | Reviews drafts for completeness, compliance |
| Brainstorm Partner | Creative exploration of embodiments |

### Architecture
```
ProfileBasedAgentFactory
  → reads AgentProfile (role, skills, tools, prompts, memory config)
  → instantiates HermesAgent with profile
AgentService
  → manages agent lifecycle, coordination, conversation history
  → supports SSE streaming for real-time thinking output
WorkflowEngine (in core/)
  → orchestrates multi-agent patent drafting pipelines
```

### Key Exports (`__init__.py`)
Hermes core classes, memory system (MemoryStore, ShortTermMemory, KnowledgeBase), profile system (AgentProfile, ProfileRegistry, ProfileBasedAgentFactory), and all 6 profile creator functions.

### Usage Pattern
```python
factory = get_agent_factory()
ceo = factory.create_agent("ceo")
result = await ceo.run(task)  # returns structured output
```
