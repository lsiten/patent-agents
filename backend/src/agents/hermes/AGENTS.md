## hermes/ — Custom Agent Framework

### Origin
Forked from NousResearch Hermes, adapted for patent-domain multi-agent orchestration. Not a pip package — lives in-tree.

### File Map
| File | Role |
|------|------|
| `agent.py` (719) | `HermesAgent` base class — message loop, tool execution, context management |
| `agent_coordinator.py` | `HermesAgentCoordinator` — multi-agent conversation, handoffs |
| `function_calls.py` | `HermesFunctionCall`/`HermesFunctionResult` — structured tool I/O |
| `message.py` | `HermesMessage`/`HermesMessageRole` — message types and roles |
| `tool.py` | `HermesTool`/`HermesToolDefinition` — tool registration and execution |
| `memory.py` | Memory system: short-term, long-term, knowledge base |
| `profiles.py` | `AgentProfile`, `AgentRole`, `AgentSkill` — agent personality definition |
| `profile_registry.py` | `ProfileRegistry` — profile catalog |
| `agent_factory.py` | `ProfileBasedAgentFactory` — profile → agent instantiation |

### Memory Architecture
```
AgentMemoryManager
├── ShortTermMemory   ← conversation context (sliding window)
├── LongTermMemory    ← persistent storage (SQLite/file)
└── KnowledgeBase     ← vector-store-backed retrieval
```

### Tool Execution Flow
```
Agent receives msg → parses tool call → executes HermesTool
→ returns HermesFunctionResult → appended to context
```
Tools live in `src/tools/` directory.
