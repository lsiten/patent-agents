## core/ — Foundation Services

### Files
| File | Lines | Responsibility |
|------|-------|----------------|
| `config.py` | — | pydantic-settings: DB, Redis, LLM, Security, Workflow configs |
| `logging.py` | — | structlog + loguru, request-id context middleware |
| `exceptions.py` | — | 20+ exception types (3 severity levels, error codes) |
| `container.py` | — | dependency-injector: DI container with 3 providers |
| `middleware.py` | — | JWT auth, rate limiting (slowapi), SSE connection manager |
| `events.py` | — | InMemoryEventBus / RedisEventBus + event types |
| `tasks.py` | — | Celery app + LocalTaskExecutor (dev fallback) |
| `workflow_engine.py` | 917 | DAG-based patent drafting workflow executor |

### Dependency Rule
`core/` imports zero `src` modules — it is the bottom layer. Everything else depends on it.

### Key Patterns
- **Config**: Singleton `settings` object loaded at startup. All modules access via `from src.core.config import settings`
- **DI**: `ApplicationContainer` wired in `backend/main.py`. Override for testing via `container.override()`
- **Events**: SSE streaming for real-time agent thinking. Two implementations: InMemoryEventBus (dev) and RedisEventBus (prod)
- **Tasks**: Celery for background tasks. LocalTaskExecutor as sync fallback when Redis unavailable
- **Workflow**: DAG-based engine — define steps as nodes, dependencies as edges, executor traverses topologically
