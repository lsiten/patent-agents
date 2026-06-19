# LangGraph / Hermes / AG-UI 接入审查

审查日期：2026-06-19

审查对象：当前代码是否符合 `docs/langgraph-hermes-agui-workflow-optimization.md`，以及 LangGraph、AG-UI 相关依赖是否已经安装并实际使用。

## 当前结论

系统已经真实接入 Hermes Agent 底座，并已安装且使用官方 LangGraph 与 AG-UI 依赖。

- Hermes `run_agent.AIAgent` 仍是专业 Agent 执行底座。
- LangGraph `StateGraph` 已成为 `PatentWorkflowEngine.execute_full_workflow()` 的公开入口。
- AG-UI 已成为工作流 SSE 事件的统一协议层，后端统一补齐协议字段，前端通过 `WorkflowProtocolStore` 归并事件。

为保证真实专利生成链路稳定，现阶段 LangGraph runtime 先以兼容 facade 接入：图负责节点身份、状态、路由入口和恢复语义；成熟的 Hermes 专业 Agent 执行逻辑仍通过内部 seam 调用。后续可继续把每个专业阶段拆成独立 LangGraph node。

## 证据

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| Hermes Agent 底座 | 符合 | `backend/src/agents/agent_config.py` 从 `run_agent` 导入并创建 `AIAgent`。 |
| 官方 LangGraph 依赖 | 符合 | `backend/pyproject.toml`、`backend/requirements.txt` 声明 `langgraph>=1.2,<2`。 |
| 官方 LangGraph 使用 | 符合 | `backend/src/core/workflow_graph/runtime.py` 使用 `StateGraph/START/END` 建模主链路。 |
| 工作流图状态 | 符合基础要求 | `PatentWorkflowState` 包含 `task_id`、`conversation_id`、`current_node`、`shared_facts`、`phase_rounds`、`route_history`、`interrupt`、`artifacts`、`quality_score`。 |
| 官方 AG-UI 依赖 | 符合 | `frontend/package.json` 声明 `@ag-ui/core@^0.0.57`、`@ag-ui/client@^0.0.57`。 |
| AG-UI 事件字段 | 符合 | `backend/src/core/workflow/protocol/agui_events.py` 输出 `agui_type/run_id/message_id/tool_call_id/parent_message_id/state_delta`。 |
| 前端协议归并 | 符合基础要求 | `frontend/lib/workflowProtocolStore.ts` 使用官方类型消费并归并 SSE 事件。 |

## 当前主链路节点

`PatentWorkflowGraphRuntime` 声明的节点顺序：

```text
brainstorm
title_generation
human_confirm_start
requirement_analysis
requirement_gate
retrieval
retrieval_gate
writing
writing_gate
quality_review
quality_gate
final_docx
```

## AG-UI 事件族

后端 adapter 当前覆盖：

- `RUN_STARTED`
- `STATE_DELTA`
- `TEXT_MESSAGE_START`
- `TEXT_MESSAGE_CONTENT`
- `TEXT_MESSAGE_END`
- `TOOL_CALL_START`
- `TOOL_CALL_ARGS`
- `TOOL_CALL_RESULT`
- `TOOL_CALL_END`
- `PHASE_ROUND_STARTED`
- `PHASE_ROUND_COMPLETED`
- `QUALITY_GATE_COMPLETED`
- `SHARED_FACTS_UPDATED`
- `HUMAN_INPUT_REQUESTED`
- `RUN_FINISHED`

## 剩余迁移边界

1. 专业阶段仍需继续深拆

   现阶段 `requirement_analysis` 节点内部调用原成熟全流程，目的是保证真实浏览器生成专利、DOCX 生成和质量门不回退。下一步应把需求、检索、撰写、质检分别迁移为独立 node 实现。

2. Gate 逻辑仍需模块化

   图中已有 `requirement_gate/retrieval_gate/writing_gate/quality_gate` 节点，但大量判断仍在旧 engine 内部。后续应迁移到 `workflow_graph/gates/`。

3. API routes 仍需按域拆分

   `routes.py` 仍然过大，应继续拆为 `workflows/conversations/agents/system_config/search` 等域模块。

4. 前端页面仍需继续组件化

   `WorkflowProtocolStore` 已接入，但 workflow 页面仍承担较多展示逻辑。后续应继续拆出 `MessageTimeline`、`Composer`、`WorkflowStartBanner`、`PhaseOutputViews`。

## 已验证

- `backend/.venv/bin/pytest backend/tests/test_langgraph_agui_integration.py -q`
- `backend/.venv/bin/pytest backend/tests/test_workflow_agent_work_log.py backend/tests/test_workflow_quality_gate.py -q`
- `frontend/ ./node_modules/.bin/tsc --noEmit`
