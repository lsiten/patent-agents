# api/ — REST And SSE Routes

## Structure

Routes are split by domain under `api/routers/`. Do not add new endpoint groups to a monolithic catch-all route file.

Common domains:

| Domain | Purpose |
| --- | --- |
| conversations | Chat conversations, messages, active reply state, conversation event streams |
| workflows | Patent workflow creation, status, SSE stream, user continuation, artifact download |
| agents | Agent list, profile details, per-Agent LLM/image configuration |
| system | System status and global LLM/image configuration |
| search/knowledge | Search and knowledge endpoints when exposed directly |

## Streaming

Workflow and conversation streams use SSE. Backend events should be normalized into the AG-UI-compatible protocol fields before the frontend consumes them:

- `agui_type`
- `run_id`
- `message_id`
- `tool_call_id`
- `parent_message_id`
- `state_delta`

Frontend state is restored through `WorkflowProtocolStore`, not by guessing from ad-hoc legacy fields.

## Route Rules

- Keep endpoint handlers thin; business behavior belongs in `services/`, `core/workflow/`, repositories, or Hermes tools.
- Do not bypass the workflow runtime to generate patent content directly.
- Do not trigger formal patent generation without the required brainstorm/title/user-confirmation state.
- Do not hardcode provider lists in route modules; use `src.core.llm.providers.catalog`.
- System config saves should call runtime reload so cached LLM/image clients pick up the new values.
