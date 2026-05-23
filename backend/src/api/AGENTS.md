# api/ — REST Endpoints

## Structure
Single-file router at `routes.py` (934L). No route splitting — all endpoints in one file.

## Endpoint Groups
| Prefix | Purpose |
|--------|---------|
| `/api/auth/*` | Login, register, refresh token |
| `/api/patents/*` | CRUD patent applications + workflow trigger |
| `/api/agents/*` | Agent interaction, streaming, history |
| `/api/knowledge/*` | Prior art search, knowledge base queries |
| `/api/users/*` | User profile, settings |
| `/api/documents/*` | Generated document download/manage |

## SSE Streaming
Agent thinking updates stream via SSE at `/api/agents/{id}/stream`.
Consumer: `frontend/app/agents/page.tsx` reads `EventSource` or fetch + ReadableStream.

## Auth
JWT via `python-jose`. Middleware in `core/middleware.py`:
- `get_current_user` — required auth
- `get_current_user_optional` — optional (for public routes)
- `require_role` / `require_admin` — role-based guards

## Request Flow
```
HTTP Request → CORS middleware → Auth middleware → Rate limiter → Route handler
                                                   ↘ SSE connection manager (for streaming)
```
