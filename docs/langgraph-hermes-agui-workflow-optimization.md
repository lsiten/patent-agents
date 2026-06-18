# LangGraph + Hermes + AG-UI 专利工作流优化方案

## 目标

当前系统的目标是通过真实 Hermes Agent 团队协作，产出可用于申请的发明专利 DOCX。优化后的系统必须满足：

- 不根据提示词或交底文件自动启动正式申请流程，启动前必须完成头脑风暴、专利名称生成和用户确认。
- CEO Agent 只做调度、上下文维护、质量门路由和状态管理，不替专业 Agent 下专业结论。
- 每个阶段有明确输入/输出契约、质量门、失败反馈路由和轮次持久化。
- 所有 Agent 共享同一份已确认公共事实，每轮在上一轮结果与反馈基础上继续优化。
- 质量审查不合格时必须路由回对应 Agent 修复，再复审，直到无关键问题或评分达到 90 分以上。
- 无 mock、无内容兜底、无案例专用规则。确定性硬规则可本地检查；内容质量、创造性、充分公开、检索风险等判断必须由 Agent LLM 完成。
- 前端必须实时展示检索过程、检索结果、分段撰写过程、工具调用、技能调用、质量问题路由和每阶段多轮结果。

## 分层架构

```text
用户
  ↓
Next.js 前端
  ↓ AG-UI 风格事件流
FastAPI Workflow API
  ↓
LangGraph 式 Workflow Runtime
  ├─ WorkflowState
  ├─ SharedFacts
  ├─ PhaseContract
  ├─ QualityGate
  ├─ Checkpoint
  ├─ Interrupt
  └─ RouteDecision
      ↓
Hermes Agents
  ├─ CEO Agent
  ├─ Brainstorm Partner
  ├─ Requirement Analyst
  ├─ Retrieval Analyst
  ├─ Patent Writer
  └─ Quality Reviewer
      ↓
Hermes Tools / MCP Tools
  ├─ 专利库检索
  ├─ 论文检索
  ├─ 网页/权威来源检索
  ├─ 附图生成
  ├─ DOCX 生成
  └─ 规范硬规则检查
```

## 协议分层

| 层级 | 职责 | 建议 |
| --- | --- | --- |
| Agent 底座 | 专业 Agent 执行、profile、SOUL、skills、tools | 保持 Hermes Agent |
| 流程骨架 | 节点、边、循环、checkpoint、interrupt、条件路由 | 采用 LangGraph 式状态图 |
| 内部通信 | Agent 间阶段输入/输出、质量门、共享事实增量 | 强类型 Workflow Contract |
| 前端通信 | 实时日志、工具展开、轮次 tab、刷新恢复 | AG-UI 风格事件 |
| 工具连接 | 外部工具、数据源、文件生成 | Hermes Tool / MCP |
| 未来互联 | 外部 Agent 服务互操作 | 需要服务化时再接 A2A |

## LangGraph 式状态图

```text
START
  ↓
brainstorm
  ↓
title_generation
  ↓
human_confirm_start
  ↓
requirement_analysis
  ↓
requirement_gate
  ├─ missing_info → retrieval
  ├─ need_user → user_interrupt
  └─ passed → writing

retrieval
  ↓
retrieval_gate
  ├─ insufficient → retrieval
  ├─ need_requirement_review → requirement_analysis
  ├─ need_user → user_interrupt
  └─ passed → writing

writing
  ↓
writing_gate
  ├─ requirement_issue → requirement_analysis
  ├─ evidence_issue → retrieval
  └─ passed → quality_review

quality_review
  ↓
quality_gate
  ├─ writer_issue → writing
  ├─ retrieval_issue → retrieval
  ├─ requirement_issue → requirement_analysis
  ├─ user_issue → user_interrupt
  └─ score >= 90 and no critical issue → final_docx

final_docx
  ↓
END
```

## WorkflowState

所有阶段共享一个工作流状态对象。状态只能追加轮次和合并已确认事实，不能用新一轮输出覆盖历史。

```json
{
  "task_id": "",
  "conversation_id": "",
  "status": "brainstorming | awaiting_confirmation | running | waiting_user | completed | failed",
  "current_node": "",
  "current_round": 0,
  "shared_facts_version": 0,
  "shared_facts": {},
  "phase_rounds": {
    "brainstorm": [],
    "requirement_analysis": [],
    "retrieval": [],
    "writing": [],
    "quality_review": []
  },
  "open_gaps": [],
  "resolved_gaps": [],
  "retrieval_evidence": [],
  "draft_sections": {},
  "drawings": [],
  "review_issues": [],
  "route_history": [],
  "interrupt": null
}
```

## SharedFacts

SharedFacts 是所有 Agent 的公共事实源。每个 Agent 只能提交 `shared_facts_delta`，由 CEO 在质量门通过后合并。

```json
{
  "patent_title": "",
  "patent_type": "发明专利",
  "public_status": "未公开",
  "technical_field": "",
  "technical_problem": "",
  "technical_solution": "",
  "innovation_points": [],
  "claim_strategy": {
    "independent_claim_steps": 4,
    "claim_semicolon_period_linebreak": true
  },
  "confirmed_terms": [],
  "forbidden_terms": [],
  "retrieval_evidence": [],
  "resolved_questions": [],
  "unresolved_questions": []
}
```

合并规则：

- 空值不覆盖已有事实。
- 未通过质量门的输出不能进入 SharedFacts。
- 用户确认信息优先级最高。
- 需求分析确认的事实高于检索建议。
- 检索证据只作为证据事实，不直接替代需求结论。
- 撰写草稿不能反向修改事实，只能暴露缺口或矛盾。
- 质量审查只能产生问题和路由建议，不能自行改写事实。

## 阶段契约

### 头脑风暴

输入：

- 用户原始描述或交底文件。
- 历史对话。
- 可选检索结果。

输出：

```json
{
  "patent_title": "",
  "technical_theme": "",
  "core_innovation_points": [],
  "protection_direction": "",
  "patent_type_recommendation": "",
  "public_status_question": "",
  "questions_for_user": [],
  "ready_to_confirm_start": false
}
```

质量门：

- 必须生成清晰专利名称。
- 必须明确技术主题和至少一个核心创新点。
- 必须明确启动前仍需用户确认的问题。
- 不能自动启动正式流程。

### 需求分析

输入：

- SharedFacts。
- 原始交底信息。
- 头脑风暴输出。
- 检索证据。
- 上轮反馈。

输出：

```json
{
  "technical_field": "",
  "technical_problem": "",
  "existing_defects": [],
  "solution_direction": "",
  "innovation_points": [],
  "missing_information": [],
  "must_resolve_before_writing": [],
  "retrieval_feedback_review": {
    "all_requirement_gaps_closed": false,
    "remaining_requirement_gaps": [],
    "search_feedback_for_retrieval": [],
    "ready_for_writing": false
  },
  "shared_facts_delta": {}
}
```

质量门：

- 能说明需求是什么、要解决什么、还缺什么。
- 对检索回传证据进行复核。
- `must_resolve_before_writing` 为空或可被检索阶段继续解决后，才允许进入撰写。

### 检索分析

输入：

- 需求分析提出的缺口。
- SharedFacts。
- 上一轮检索失败的查询和数据源状态。

输出：

```json
{
  "query_plan": [],
  "sources_used": [],
  "unavailable_sources": [],
  "retrieval_results": [],
  "confirmed_sources": [],
  "non_patent_prior_art": [],
  "web_evidence": [],
  "evidence_summary": "",
  "resolved_questions": [],
  "unresolved_questions": [],
  "next_query_suggestions": [],
  "shared_facts_delta": {}
}
```

质量门：

- 已配置专利库可用时优先检索。
- 未配置或不可用的数据源要记录并跳过，不能阻塞全部检索。
- 专利库无结果时继续论文检索。
- 论文无结果时继续 Google Patents、公开网页和权威技术网站。
- 所有来源都不足时，基于可靠信息和真实世界物理规律尝试解决；仍无法解决才请求用户补充。
- 无检索结果不能直接失败，必须分析原因并调整检索条件。

### 专利撰写

输入：

- SharedFacts。
- 需求分析确认结果。
- 检索证据。
- 质量审查反馈。
- 专利撰写规范。

输出：

```json
{
  "sections_written": [],
  "claims": {},
  "description": {},
  "drawings_plan": [],
  "drawings": [],
  "docx_draft_path": "",
  "self_check": {},
  "shared_facts_delta": {}
}
```

质量门：

- 分段撰写并落库，不允许一次性黑盒输出。
- 权利要求 1 独权只能由 3 步或 4 步组成。
- 权利要求书中每个分号和句号必须换行。
- 不允许出现逐字稿时间戳、说话人、沟通口语等格式性内容。
- 附图必须根据真实专利内容逐图生成，不允许使用内置案例模板或同图换标题。
- DOCX 草稿必须同步刷新。

### 质量审查

输入：

- 结构化专利草稿。
- DOCX 草稿。
- 附图文件。
- SharedFacts。
- 撰写规范。

输出：

```json
{
  "score": 0,
  "recommendation": "approve | revise | ask_user",
  "critical_issues": [],
  "minor_issues": [],
  "issues": [
    {
      "type": "",
      "severity": "critical | high | medium | low",
      "responsible_phase": "requirement_analysis | retrieval_analysis | patent_writing | user_input | system_failure",
      "instruction": ""
    }
  ],
  "route_to": "requirement_analysis | retrieval_analysis | patent_writing | user_input | complete"
}
```

质量门：

- 分数达到 90 分以上且无 critical/high 阻塞问题才通过。
- 审查出问题不能结束流程，必须路由回责任 Agent。
- 必须审查附图是否缺失、重复、与正文不一致。
- 必须审查 DOCX 中附图是否插入对应位置。
- 必须审查权利要求格式硬规则和说明书规范。

## Interrupt

以下场景必须进入中断状态，等待用户动作后 resume：

- 启动正式流程前确认。
- 专利名称缺失或需用户确认。
- 专利类型或公开状态不明确。
- 多轮检索后仍无法确定影响权利要求骨架的事实。
- 质量审查判断必须由用户补充业务事实。

启动确认条必须展示：

- 专利名称。
- 专利类型。
- 公开状态。
- 技术主题。
- 核心创新点。
- 确认启动按钮。
- 稍后/继续讨论入口。

## 条件路由

质量问题必须归属责任阶段：

| 问题类型 | 路由 |
| --- | --- |
| 需求不清、创新点不清、保护对象不清 | requirement_analysis |
| 证据不足、检索来源不足、现有技术不清 | retrieval_analysis |
| 权利要求、说明书、附图、DOCX 插入问题 | patent_writing |
| 用户专属事实缺失 | user_input |
| 工具失败、文件生成失败、配置错误 | system_failure |

## 循环保镖

```json
{
  "max_total_rounds": 20,
  "max_requirement_rounds": 5,
  "max_retrieval_rounds": 6,
  "max_writing_rounds": 5,
  "max_review_rounds": 5,
  "no_progress_limit": 2,
  "api_max_retries": 3
}
```

超过限制时必须输出：

- 已尝试路径。
- 已确认事实。
- 仍无法解决的问题。
- 是否需要用户补充。

不能无限重试。

## AG-UI 风格事件

后端 SSE 应统一输出以下事件族：

```text
RUN_STARTED
STATE_DELTA
TEXT_MESSAGE_START
TEXT_MESSAGE_CONTENT
TEXT_MESSAGE_END
TOOL_CALL_START
TOOL_CALL_ARGS
TOOL_CALL_RESULT
TOOL_CALL_END
PHASE_ROUND_STARTED
PHASE_ROUND_COMPLETED
QUALITY_GATE_COMPLETED
SHARED_FACTS_UPDATED
HUMAN_INPUT_REQUESTED
RUN_FINISHED
```

现有事件可保留兼容字段，但必须额外携带 AG-UI 映射字段：

```json
{
  "agui_type": "TOOL_CALL_START",
  "run_id": "",
  "message_id": "",
  "tool_call_id": "",
  "parent_message_id": "",
  "state_delta": {}
}
```

前端必须基于事件恢复：

- 当前阶段。
- 当前轮次。
- 工具展开内容。
- 检索结果列表。
- 分段撰写结果。
- 质量问题路由。
- 启动确认/用户补充 interrupt。

## Hermes 团队模式应用

- Queue：同一专利任务内阶段顺序执行。
- Background：耗时检索、附图生成可后台执行，但必须持久化事件和 checkpoint。
- delegate_task：仅用于上下文防火墙清晰的并行检查，例如附图重复检查、DOCX 媒体检查、证据真伪抽查。
- Context Firewall：子任务只接收目标和必要上下文，返回结构化报告，不能修改 SharedFacts。
- Dev 监控面板：仅开发环境展示，放在页面底部，默认折叠。

## 清理原则

必须删除：

- mock 检索。
- mock 生图。
- mock 质量审查。
- 内容 fallback。
- 固定案例术语和逻辑。
- 内置案例附图。
- 旧规范修复逻辑。
- 不符合新架构的旧测试。
- 未被主链路引用的脚本。

必须保留：

- `_api_max_retries = 3`。
- 确定性硬规则检查。
- 数据源未配置时禁用。
- 数据源不可用时记录并跳过。
- DOCX 文件结构检查。
- 浏览器工具禁止自动扫描调试端口的安全限制。

## 验收标准

每次完整实现后，必须通过真实浏览器生成一份专利并验证：

- 启动前有专利名和用户确认。
- 正式流程不会被提示词直接触发。
- 每个阶段每轮有记录并可在前端查看。
- 检索过程和检索结果列表可见。
- 分段撰写过程可见。
- 质量审查问题能路由回责任 Agent。
- 所有修复轮次写入 SharedFacts 或阶段历史。
- 最终 DOCX 可下载。
- DOCX 符合《专利申请文件撰写完整规范手册.md》。
- 权利要求 1 为 3 或 4 步。
- 权利要求书中每个分号和句号已换行。
- 附图编号、标题、正文引用、文件插入一致。
- 无 mock、无内容兜底、无案例专用逻辑。
