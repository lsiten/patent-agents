# Agent 活动日志架构设计

**版本**: v1.0
**最后更新**: 2026-06-05

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [整体架构](#2-整体架构)
3. [数据模型](#3-数据模型)
4. [SSE 事件流管道](#4-sse-事件流管道)
5. [前端组件架构](#5-前端组件架构)
6. [数据流详解](#6-数据流详解)
7. [关键边界情况](#7-关键边界情况)
8. [文件清单](#8-文件清单)

---

## 1. 背景与目标

### 1.1 问题

对话脑暴（Conversation Brainstorm）场景中，用户与 Agent 进行多轮对话。Agent 在生成回复过程中会产生一系列**中间活动**：

- **思考过程**（thinking）：Agent 正在推理的阶段性思考
- **工具调用**（tool_call）：Agent 调用专业技能/工具、工具返回结果
- **状态流转**（status）：Agent 的处理状态变化
- **技能使用**（skill_use）：Agent 选择并应用专业技能

在初始实现中，这些活动仅在 SSE 流中实时推送，**未被持久化**，导致：

- 对话重载后历史活动的可见性丢失
- 无法回放 Agent 的完整推理链条
- 调试和审计缺乏中间状态数据

### 1.2 目标

1. **实时可见**：用户能在 SSE 流式响应中即时看到 Agent 的中间活动
2. **持久化**：活动记录随消息写入数据库，对话重载后可恢复
3. **统一模型**：前端和后端使用统一的事件模型，消除类型断层
4. **可扩展**：事件类型可扩展，新增回调只需追加而不破坏已有流程

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          前端 (Next.js)                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                    Chat Page (page.tsx)                   │      │
│  │                                                          │      │
│  │  ┌──────────┐   SSE Callbacks                 ┌───────┐ │      │
│  │  │ Message   │ ◄── onThinking / onSkillUse    │ Agent │ │      │
│  │  │ List      │      onToolCallStart/End       │Activity│ │      │
│  │  │           │      onStatus / onDone          │ Log   │ │      │
│  │  │ [Msg 1]   │                                │ ───── │ │      │
│  │  │   ┌─────┐ │   agent_events[] ──────────►   │thinking│ │      │
│  │  │   │Activity│                               │tool_...│ │      │
│  │  │   │ Log  │ │                                │ ───── │ │      │
│  │  │   └─────┘ │                                └───────┘ │      │
│  │  │ [Msg 2]   │                                          │      │
│  │  │   ┌─────┐ │                                          │      │
│  │  │   │Activity│                                          │      │
│  │  │   │Log   │ │                                          │      │
│  │  │   └─────┘ │                                          │      │
│  │  └──────────┘                                          │      │
│  └──────────────────────────────────────────────────────────┘      │
│                           ▲ ▲ ▲ ▲                                  │
│                           │ │ │ │ SSE 流                            │
└───────────────────────────┼─┼─┼─┼──────────────────────────────────┘
                            │ │ │ │
┌───────────────────────────┼─┼─┼─┼──────────────────────────────────┐
│                           ▼ ▼ ▼ ▼                                  │
│                     FastAPI Backend                                │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              SSE Streaming Endpoint                       │      │
│  │  POST /conversations/{conv_id}/chat/stream                │      │
│  │                                                          │      │
│  │  Agent Run Loop ──► on_thinking() ──► SSE event          │      │
│  │                   ──► on_tool_start() ──► SSE event      │      │
│  │                   ──► on_tool_end() ──► SSE event        │      │
│  │                   ──► on_status() ──► SSE event          │      │
│  │                   ──► on_done() ──► persist + SSE event  │      │
│  │                                                          │      │
│  │  ┌──────────────────┐                                    │      │
│  │  │ conversations_store │ (dict in memory)                │      │
│  │  │ agent_events[]     │ ◄── 回调写入                     │      │
│  │  │ agent_events[] into│                                    │      │
│  │  │ assistant_msg      │ ──► _persist_conversation()     │      │
│  │  └──────────────────┘                                    │      │
│  └──────────────────────────────────────────────────────────┘      │
│                      │                                              │
│                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │  Persistence Layer                                        │      │
│  │  DB: File-based JSON (conversations_store + DB backup)   │      │
│  │  agent_events 序列化为 JSON 存入 message.metadata        │      │
│  └──────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 两条管线对比

本系统存在两类 Agent 活动展示场景，它们的实现路径不同但共享事件模型：

| 特性 | 对话脑暴 (Conversation Brainstorm) | 工作流 (Workflow) |
|------|-----------------------------------|--------------------|
| SSE 端点 | `/chat/stream` | `/workflows/{task_id}/stream` |
| 事件模型 | `AgentEventInfo` / `AgentEvent` | `TaskEvent` (数据库实体) |
| 持久化 | 随 `ConversationMessage` 存入 | 独立 `task_events` 表 |
| 前端展示 | `AgentActivityLog` (内嵌消息) | `ProgressStepper` + `MessageLog` |
| 回放机制 | 对话加载时一并返回 | 工作流详情接口返回事件列表 |

---

## 3. 数据模型

### 3.1 后端 Pydantic 模型

文件: `backend/src/api/schemas.py`

#### `AgentEventInfo` — Agent 事件记录单元

```python
class AgentEventInfo(BaseModel):
    """Agent事件记录（用于持久化和回放）"""
    type: str           # thinking | tool_call_start | tool_call_end | skill_use | status | dispatch
    agent_name: str     # 产生事件的 Agent 名称（如 patent.ceo.v1）
    timestamp: str      # ISO 8601 时间戳
    message: str        # 人类可读的事件描述
    data: Dict[str, Any] = {}  # 原始数据负载（用于前端渲染）
```

#### `ConversationMessage` — 消息容器（扩展后）

```python
class ConversationMessage(BaseModel):
    """对话消息"""
    id: str
    role: str                    # user / assistant / system
    content: str
    timestamp: str
    type: str = "text"
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[ToolCallInfo]] = None
    agent_events: Optional[List[AgentEventInfo]] = None  # ← 新增
```

### 3.2 前端 TypeScript 类型

文件: `frontend/types/index.ts`

```typescript
export interface AgentEvent {
  type: 'thinking' | 'tool_call_start' | 'tool_call_end' | 'skill_use' | 'status' | 'dispatch';
  agent_name: string;
  timestamp: string;
  message: string;
  data: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  // ... 其他字段
  agent_events?: AgentEvent[];  // ← 新增
  isStreaming?: boolean;
}
```

### 3.3 模型对照表

| 后端 `AgentEventInfo` | 前端 `AgentEvent` | 说明 |
|-----------------------|-------------------|------|
| `type: str` | `type: 'thinking' \| ...` | 事件类型 |
| `agent_name: str` | `agent_name: string` | Agent 名称 |
| `timestamp: str` | `timestamp: string` | ISO 8601 |
| `message: str` | `message: string` | 可读描述 |
| `data: Dict[str, Any]` | `data: Record<string, unknown>` | 原始数据 |

---

## 4. SSE 事件流管道

### 4.1 后端 SSE 回调管道 (`backend/src/api/routes.py`)

Agent 运行循环中，每个关键阶段触发对应的回调函数。每个回调函数执行两个操作：

1. **写入 SSE 流**：向前端推送实时事件
2. **收集 `agent_events`**：将事件元数据追加到消息的 `agent_events` 数组

#### 4.1.1 `on_thinking` — Agent 思考中

```python
def on_thinking(text: str):
    # SSE 推送
    events.append({"type": "thinking", "data": {"agent": "patent.ceo.v1", "message": text[:300]}})
    # 收集 agent_event
    current_agent_events.append(AgentEventInfo(
        type="thinking", agent_name="patent.ceo.v1",
        timestamp=datetime.now().isoformat(),
        message=text[:200], data={"full_text": text[:300]}
    ))
```

#### 4.1.2 `on_tool_start` — 工具开始执行

```python
def on_tool_start(tool_call: ToolCall):
    events.append({"type": "tool_call_start", "data": {
        "name": tool_call.function.name,
        "parameters": tool_call.function.arguments
    }})
    current_agent_events.append(AgentEventInfo(
        type="tool_call_start", agent_name="patent.ceo.v1",
        timestamp=..., message=f"调用工具: {tool_call.function.name}",
        data={"name": tool_call.function.name, "arguments": tool_call.function.arguments}
    ))
```

#### 4.1.3 `on_tool_complete` — 工具完成

```python
def on_tool_complete(tool_call):
    events.append({"type": "tool_call_end", "data": {"name": ..., "result": ...}})
    current_agent_events.append(AgentEventInfo(
        type="tool_call_end", ...,
        message=f"工具完成: {tool_call.function.name}",
        data={"name": ..., "result": ..., "success": ...}
    ))
```

#### 4.1.4 `on_status` — 状态变化

```python
def on_status(agent: str, status: str, message: str):
    events.append({"type": "status", "data": {"agent": agent, "status": status, "message": message}})
    current_agent_events.append(AgentEventInfo(
        type="status", agent_name=agent,
        timestamp=..., message=message or status,
        data={"agent": agent, "status": status, "message": message}
    ))
```

### 4.2 持久化时机

```
Stream Start
  │
  ├── Agent 运行循环开始
  │     │
  │     ├── on_thinking()      → agent_events.append()
  │     ├── on_tool_start()    → agent_events.append()
  │     ├── on_tool_complete() → agent_events.append()
  │     ├── on_status()        → agent_events.append()
  │     └── ... (循环)
  │
  └── on_done()
        │
        ├── 构造 assistant_msg = ConversationMessage(agent_events=current_agent_events)
        ├── conversations_store[conv_id]['messages'].append(assistant_msg)
        ├── _persist_conversation(conv_id)  → 写数据库
        └── SSE 推送 'done' 事件 (含 message 对象)
```

### 4.3 前端 SSE 接收管道 (`frontend/lib/api.ts`)

`chatStream()` 函数解析 SSE 协议，将不同类型的事件分发到对应的回调：

```typescript
// SSE 事件分发
switch (eventType) {
  case 'thinking':      callbacks.onThinking?.(parsed);      break;
  case 'skill_use':     callbacks.onSkillUse?.(parsed);      break;
  case 'tool_call_start': callbacks.onToolCallStart?.(parsed); break;
  case 'tool_call_end':   callbacks.onToolCallEnd?.(parsed);   break;
  case 'content':       callbacks.onContent?.(parsed);       break;
  case 'status':        callbacks.onStatus?.(parsed);        break;  // ← 新增
  case 'confirmation':  callbacks.onConfirmation?.(parsed);  break;
  case 'done':          callbacks.onDone?.(parsed);          break;
  case 'error':         callbacks.onError?.(...);            break;
}
```

回调类型定义:

```typescript
callbacks: {
  onThinking?: (data: { iteration: number; agent: string; phase?: string }) => void;
  onSkillUse?: (data: { name: string; description: string; reasoning: string }) => void;
  onToolCallStart?: (data: { name: string; parameters: Record<string, unknown> }) => void;
  onToolCallEnd?: (data: { name: string; parameters: Record<string, unknown>; result: unknown; success: boolean; error?: string }) => void;
  onContent?: (data: { content: string; has_recommendation: boolean }) => void;
  onConfirmation?: (data: { question: string; options: string[] }) => void;
  onStatus?: (data: { agent: string; status: string; message: string; iteration?: number }) => void;  // ← 新增
  onDone?: (data: { message: ChatMessage; has_recommendation: boolean; needs_confirmation?: boolean; conversation_id: string }) => void;
  onError?: (error: string) => void;
  onStatusChange?: (status: 'connecting' | 'connected' | 'disconnected') => void;
}
```

---

## 5. 前端组件架构

### 5.1 `AgentActivityLog` 组件 (`frontend/components/chat/AgentActivityLog.tsx`)

**Props**:
```typescript
interface AgentActivityLogProps {
  events: AgentEvent[];      // 要展示的事件列表
  className?: string;        // 自定义 CSS 类
}
```

**功能特性**:

| 特性 | 实现 |
|------|------|
| 可折叠 | `expanded` state 控制展开/折叠，默认展开 |
| 实时自动滚动 | `useEffect` 监听 `events` 变化，自动滚动到底部 |
| 事件图标映射 | `thinking`→🧠紫色, `tool_call_start`→⚡琥珀色, `tool_call_end`→✅绿色, `status`→ℹ️蓝色 |
| 进行中指示器 | `runningCount > doneCount` 时显示"N 进行中" |
| 无事件时隐藏 | `events.length === 0` 返回 `null` |
| 时间戳格式化 | `toLocaleTimeString('zh-CN')` 显示 HH:MM:SS |
| 消息截断 | `min-w-0 truncate` CSS 截断长文本 |

**渲染结构**:
```
┌──────────────────────────────────────┐
│ ▼ Agent 活动日志    5 条事件  2 进行中 │  ← 折叠按钮
├──────────────────────────────────────┤
│ 🧠 14:30:01  思考中...               │
│ ⚡ 14:30:02  调用工具: patent_search  │
│ ℹ️ 14:30:03  正在检索专利数据库...     │
│ ✅ 14:30:05  工具完成: patent_search  │
│ ⚡[动画] 14:30:06  调用工具: analyze   │  ← 进行中(旋转动画)
└──────────────────────────────────────┘
```

### 5.2 集成方式 (`frontend/app/chat/page.tsx`)

**初始化**：在流消息创建时初始化空数组

```typescript
const msg = createLocalChatMessage('assistant', '', {
  tool_calls: [],
  agent_events: [],  // ← 新增
  metadata: { ... },
});
```

**事件追加**：每个 SSE 回调中重建 AgentEvent 并追加

```typescript
onThinking: (_data) => {
  setMessages((prev) => prev.map((m) =>
    m.id === streamMsgId
      ? {
          ...m,
          agent_events: [
            ...(m.agent_events || []),
            {
              type: 'thinking',
              agent_name: 'patent.ceo.v1',
              timestamp: new Date().toISOString(),
              message: '思考中...',
              data: _data as Record<string, unknown>,
            },
          ],
        }
      : m
  ));
},
```

**渲染**：在消息卡片中嵌入 `AgentActivityLog`

```tsx
{/* Agent 活动日志 */}
{msg.agent_events && msg.agent_events.length > 0 && (
  <AgentActivityLog events={msg.agent_events} />
)}
```

---

## 6. 数据流详解

### 6.1 全链路追踪

以一次用户提问为例，Agent 调用工具搜索专利：

```
步骤  |   后端动作                  |   前端动作                  |   数据库
──────┼────────────────────────────┼────────────────────────────┼──────────
1     | 用户发送消息                | POST /chat/stream          │
      |                            | onStatusChange('connecting')│
2     | Agent 开始 "思考"          |                            │
      | on_thinking("分析用户需求") |                            │
      | → SSE event: thinking      | → onThinking()             │
      | → agent_events += [type:thinking] │ append agent_event to msg│
3     | Agent 调用工具             |                            │
      | on_tool_start("patent_search")│                         │
      | → SSE event: tool_call_start│ → onToolCallStart()       │
      | → agent_events += [tool_call_start]│ → append agent_event      │
4     | 工具执行中...              |                            │
      | on_status("searching", ...)│                            │
      | → SSE event: status       │ → onStatus()               │
      | → agent_events += [status]│ → append agent_event      │
5     | 工具返回结果               |                            │
      | on_tool_complete(...)     │                            │
      | → SSE event: tool_call_end │ → onToolCallEnd()          │
      | → agent_events += [tool_call_end]│ → append agent_event      │
6     | Agent 生成回复            |                            │
      | → SSE event: content      | → onContent()              │
7     | 完成                      |                            │
      | on_done()                 | → onDone()                 │
      | assistant_msg.agent_events│ → replace msg with final   │
      | = current_agent_events    |    (含 agent_events)       │
      | → _persist_conversation() │                            │
      | → 写入 DB                 │                            │ ← 已持久化
──────┼────────────────────────────┼────────────────────────────┼──────────
8     | 用户重新打开对话           | GET /conversations/{id}    │
      | 返回含 agent_events 的消息│ → 渲染消息列表 + 活动日志   │
```

### 6.2 关键设计决策

#### 为什么 agent_events 不独立建表？

对话脑暴场景中的 Agent 事件是消息的附属数据，生命周期与消息绑定：

- **读取时总是一起返回**：不需要独立查询事件列表
- **数量有限**：每条消息的事件通常在 10-50 条量级
- **结构简单**：无需独立索引或复杂查询

独立事件表的方案（`task_events`）用于工作流场景，因为工作流事件需要独立查询（按类型过滤、跨任务聚合等）。

#### 为什么 SSE 回调中实时追加而不是一次性发送？

- **即时性**：用户可以在 Agent 思考的同时看到中间状态
- **流式体验**：活动日志随时间推进自然滚动，而不是在结束时一瞬间弹出
- **容错**：即使 SSE 流中断，已推送的事件已在前端可见

---

## 7. 关键边界情况

| 场景 | 处理方式 |
|------|----------|
| **无事件的消息** | `agent_events` 为 `undefined` 或 `[]`，`AgentActivityLog` 返回 `null` |
| **对话重载** | 后端返回包含 `agent_events` 的 `ConversationMessage`，前端直接渲染历史活动 |
| **SSE 流中断** | 前端 `stallTimeout` 触发错误回调，但已追加的 `agent_events` 保留在消息中 |
| **并发写入** | 后端 `events_lock` 保护 `current_agent_events` 列表的写入 |
| **消息替换** | `onDone` 用后端返回的最终消息替换 `streamMsg`（含完整的 `agent_events`），确保持久化数据为准 |
| **超大事件数据** | `data` 字段限制长度（后端 `text[:200]`），避免单个事件膨胀过大 |
| **无 `onStatus` 的前端** | 已补齐 `onStatus` 回调和 SSE 分发，旧版本不会收到 `status` 事件 |

---

## 8. 文件清单

### 新增

| 文件 | 行数 | 说明 |
|------|------|------|
| `frontend/components/chat/AgentActivityLog.tsx` | 128 | Agent 活动日志展示组件 |

### 修改

| 文件 | 变更内容 |
|------|----------|
| `backend/src/api/schemas.py` | 新增 `AgentEventInfo`、`ConversationMessage.agent_events` |
| `backend/src/api/routes.py` | 4 个 SSE 回调收集 agent_events、持久化逻辑修复 |
| `frontend/types/index.ts` | 新增 `AgentEvent`、`ChatMessage.agent_events` |
| `frontend/lib/api.ts` | 新增 `onStatus` 回调类型和 SSE 事件分发 |
| `frontend/app/chat/page.tsx` | 集成 agent_events 全链路（初始化→追加→渲染→恢复） |

### 相关现有文件

| 文件 | 说明 |
|------|------|
| `backend/src/core/events.py` | 事件总线（`InMemoryEventBus` / `RedisEventBus`） |
| `backend/src/core/workflow_engine.py` | 工作流引擎（含独立的事件持久化路径） |
| `frontend/components/workflow/MessageLog.tsx` | 工作流场景的日志组件 |

---

## 附录 A：事件类型参考

| type | 触发时机 | message 示例 | 图标 |
|------|----------|-------------|------|
| `thinking` | Agent 产生中间推理 | "正在分析用户的技术方案..." | 🧠 |
| `tool_call_start` | Agent 开始调用工具 | "调用工具: patent_search" | ⚡ |
| `tool_call_end` | 工具执行完成 | "工具完成: patent_search" | ✅ |
| `status` | Agent 状态变化 | "正在检索专利数据库..." | ℹ️ |
| `skill_use` | Agent 选择技能 | "使用技能: 专利检索" | 🔧 |
| `dispatch` | CEO Agent 分派子任务 | "分派任务给检索分析师" | 📤 |

---

**文档版本**: v1.0
**最后更新**: 2026-06-05
