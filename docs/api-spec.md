# API 接口规范文档

**版本**: v1.0
**基础路径**: `/api/v1`
**认证方式**: JWT Bearer Token

---

## 目录

1. [通用规范](#1-通用规范)
2. [认证接口](#2-认证接口)
3. [用户与组织接口](#3-用户与组织接口)
4. [专利任务接口](#4-专利任务接口)
5. [聊天对话接口](#5-聊天对话接口)
6. [Agent 管理接口](#6-agent-管理接口)
7. [组织架构接口](#7-组织架构接口)
8. [专利文档接口](#8-专利文档接口)
9. [专利检索接口](#9-专利检索接口)
10. [系统统计接口](#10-系统统计接口)

---

## 1. 通用规范

### 1.1 响应格式

所有 API 响应统一使用以下格式:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "message": "操作成功",
  "timestamp": "2024-01-20T10:00:00Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 请求是否成功 |
| data | any | 响应数据 |
| error | object/null | 错误信息 (成功时为 null) |
| message | string | 提示信息 |
| timestamp | string | ISO 8601 时间戳 |

### 1.2 分页格式

```json
{
  "success": true,
  "data": {
    "items": [],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  },
  "error": null
}
```

### 1.3 错误格式

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数验证失败",
    "details": [
      {
        "field": "email",
        "message": "邮箱格式不正确"
      }
    ]
  },
  "timestamp": "2024-01-20T10:00:00Z"
}
```

### 1.4 错误码定义

| HTTP 状态码 | 错误码 | 说明 |
|-------------|--------|------|
| 400 | VALIDATION_ERROR | 参数验证失败 |
| 401 | UNAUTHORIZED | 未授权 |
| 403 | FORBIDDEN | 权限不足 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 资源冲突 |
| 429 | TOO_MANY_REQUESTS | 请求频率超限 |
| 500 | INTERNAL_ERROR | 服务器内部错误 |

### 1.5 认证

```bash
# 请求头
Authorization: Bearer {access_token}
```

---

## 2. 认证接口

### 2.1 用户注册

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "name": "张三"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "name": "张三",
      "role": "user",
      "created_at": "2024-01-20T10:00:00Z"
    },
    "access_token": "jwt_token",
    "refresh_token": "refresh_token",
    "expires_at": "2024-01-21T10:00:00Z"
  }
}
```

### 2.2 用户登录

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**响应**: 同注册接口

### 2.3 刷新 Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "refresh_token"
}
```

### 2.4 获取当前用户信息

```http
GET /api/v1/auth/me
Authorization: Bearer {token}
```

### 2.5 更新用户资料

```http
PUT /api/v1/auth/profile
Authorization: Bearer {token}

{
  "name": "新名字",
  "avatar_url": "https://..."
}
```

### 2.6 修改密码

```http
POST /api/v1/auth/change-password
Authorization: Bearer {token}

{
  "old_password": "old_pass",
  "new_password": "new_pass"
}
```

---

## 3. 用户与组织接口

### 3.1 创建组织

```http
POST /api/v1/organizations
Authorization: Bearer {token}

{
  "name": "我的公司",
  "slug": "my-company",
  "description": "公司描述"
}
```

### 3.2 获取组织列表

```http
GET /api/v1/organizations
Authorization: Bearer {token}
```

### 3.3 获取组织详情

```http
GET /api/v1/organizations/{id}
Authorization: Bearer {token}
```

### 3.4 更新组织信息

```http
PUT /api/v1/organizations/{id}
Authorization: Bearer {token}

{
  "name": "新名称",
  "description": "新描述"
}
```

### 3.5 获取组织成员列表

```http
GET /api/v1/organizations/{id}/members
Authorization: Bearer {token}
```

### 3.6 添加组织成员

```http
POST /api/v1/organizations/{id}/members
Authorization: Bearer {token}

{
  "email": "member@example.com",
  "role": "member"
}
```

### 3.7 更新成员角色

```http
PUT /api/v1/organizations/{id}/members/{user_id}
Authorization: Bearer {token}

{
  "role": "admin"
}
```

### 3.8 移除成员

```http
DELETE /api/v1/organizations/{id}/members/{user_id}
Authorization: Bearer {token}
```

---

## 4. 专利任务接口

### 4.1 创建专利任务

```http
POST /api/v1/tasks
Authorization: Bearer {token}

{
  "title": "基于 AI 的专利申请系统",
  "tech_description": "详细的技术描述...",
  "patent_type": "invention",
  "priority": "normal"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "task-uuid",
    "title": "基于 AI 的专利申请系统",
    "patent_type": "invention",
    "current_state": "initial",
    "progress": 0,
    "created_at": "2024-01-20T10:00:00Z"
  }
}
```

### 4.2 获取任务列表

```http
GET /api/v1/tasks?page=1&page_size=20&state=writing&patent_type=invention
Authorization: Bearer {token}
```

**查询参数**:
- `page`: 页码 (默认 1)
- `page_size`: 每页数量 (默认 20)
- `state`: 状态筛选 (可选: initial, requirement, retrieval, writing, reviewing, completed, failed)
- `patent_type`: 专利类型筛选 (可选)
- `search`: 搜索关键词 (可选)

### 4.3 获取任务详情

```http
GET /api/v1/tasks/{id}
Authorization: Bearer {token}
```

**响应包含所有阶段产出**:
```json
{
  "id": "task-uuid",
  "title": "...",
  "current_state": "writing",
  "progress": 60,
  "requirement_doc": {},
  "retrieval_report": {},
  "patent_draft": {},
  "review_report": {},
  "final_patent": {}
}
```

### 4.4 获取任务事件流

```http
GET /api/v1/tasks/{id}/events
Authorization: Bearer {token}
```

### 4.5 SSE 实时事件流

```http
GET /api/v1/tasks/{id}/stream
Authorization: Bearer {token}
Accept: text/event-stream
```

**事件格式**:
```
event: state_change
data: {"state": "writing", "progress": 60, "message": "进入专利撰写阶段"}

event: agent_output
data: {"agent_name": "专利撰写Agent", "output": {...}}

event: completed
data: {"state": "completed", "task_id": "..."}
```

### 4.6 取消任务

```http
POST /api/v1/tasks/{id}/cancel
Authorization: Bearer {token}
```

### 4.7 删除任务

```http
DELETE /api/v1/tasks/{id}
Authorization: Bearer {token}
```

---

## 5. 聊天对话接口

### 5.1 发送消息

```http
POST /api/v1/chat/messages
Authorization: Bearer {token}

{
  "session_id": "session-uuid",
  "task_id": "task-uuid",
  "content": "帮我分析一下这个发明的创新点",
  "context": {
    "brainstorm_phase": "initial"
  }
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "user_message": {
      "id": "msg-uuid",
      "role": "user",
      "content": "帮我分析一下这个发明的创新点",
      "created_at": "2024-01-20T10:00:00Z"
    },
    "assistant_message": {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "根据您的描述...",
      "created_at": "2024-01-20T10:00:02Z"
    }
  }
}
```

### 5.2 获取聊天历史

```http
GET /api/v1/chat/messages?session_id={session_id}&page=1&page_size=50
Authorization: Bearer {token}
```

### 5.3 获取会话列表

```http
GET /api/v1/chat/sessions
Authorization: Bearer {token}
```

### 5.4 创建新会话

```http
POST /api/v1/chat/sessions
Authorization: Bearer {token}

{
  "task_id": "task-uuid",
  "title": "专利申请头脑风暴",
  "session_type": "brainstorm"
}
```

### 5.5 更新会话信息

```http
PUT /api/v1/chat/sessions/{id}
Authorization: Bearer {token}

{
  "title": "新标题"
}
```

### 5.6 删除会话

```http
DELETE /api/v1/chat/sessions/{id}
Authorization: Bearer {token}
```

---

## 6. Agent 管理接口

### 6.1 获取 Agent 列表

```http
GET /api/v1/agents?type=specialist&enabled=true
Authorization: Bearer {token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "agent-uuid",
        "name": "需求分析Agent",
        "description": "分析技术需求，提取创新点",
        "type": "specialist",
        "model": "gpt-4-turbo",
        "is_enabled": true,
        "created_at": "2024-01-20T10:00:00Z"
      }
    ],
    "total": 5
  }
}
```

### 6.2 获取 Agent 详情

```http
GET /api/v1/agents/{id}
Authorization: Bearer {token}
```

**响应包含完整配置**:
```json
{
  "success": true,
  "data": {
    "id": "agent-uuid",
    "name": "需求分析Agent",
    "description": "...",
    "system_prompt": "...",
    "model": "gpt-4-turbo",
    "temperature": 0.7,
    "max_tokens": 2048,
    "tools": [...],
    "skills": [...],
    "memory": {...}
  }
}
```

### 6.3 创建 Agent

```http
POST /api/v1/agents
Authorization: Bearer {token}

{
  "name": "我的新Agent",
  "description": "描述",
  "type": "specialist",
  "system_prompt": "系统提示词",
  "model": "gpt-4-turbo",
  "temperature": 0.7,
  "max_tokens": 2048
}
```

### 6.4 更新 Agent 配置

```http
PUT /api/v1/agents/{id}
Authorization: Bearer {token}

{
  "name": "新名称",
  "temperature": 0.8,
  "is_enabled": true
}
```

### 6.5 删除 Agent

```http
DELETE /api/v1/agents/{id}
Authorization: Bearer {token}
```

---

### 6.6 工具管理

#### 获取 Agent 工具列表
```http
GET /api/v1/agents/{id}/tools
Authorization: Bearer {token}
```

#### 添加工具
```http
POST /api/v1/agents/{id}/tools
Authorization: Bearer {token}

{
  "name": "web_search",
  "description": "网络搜索",
  "tool_type": "external",
  "config": {}
}
```

#### 更新工具
```http
PUT /api/v1/agents/{id}/tools/{tool_id}
Authorization: Bearer {token}
```

#### 启用/禁用工具
```http
POST /api/v1/agents/{id}/tools/{tool_id}/toggle
Authorization: Bearer {token}

{
  "enabled": false
}
```

#### 删除工具
```http
DELETE /api/v1/agents/{id}/tools/{tool_id}
Authorization: Bearer {token}
```

---

### 6.7 技能管理

#### 获取技能列表
```http
GET /api/v1/agents/{id}/skills
Authorization: Bearer {token}
```

#### 添加/更新/删除技能
同工具接口，路径改为 `/skills`

---

### 6.8 记忆管理

#### 获取记忆列表
```http
GET /api/v1/agents/{id}/memory?type=long_term
Authorization: Bearer {token}
```

#### 添加记忆
```http
POST /api/v1/agents/{id}/memory
Authorization: Bearer {token}

{
  "memory_type": "long_term",
  "title": "重要会议纪要",
  "content": "会议内容...",
  "importance_score": 0.9
}
```

#### 删除记忆
```http
DELETE /api/v1/agents/{id}/memory/{memory_id}
Authorization: Bearer {token}
```

#### 清空某类记忆
```http
POST /api/v1/agents/{id}/memory/clear?type=short_term
Authorization: Bearer {token}
```

---

## 7. 组织架构接口

### 7.1 获取组织架构树

```http
GET /api/v1/organization/tree
Authorization: Bearer {token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "root",
    "name": "专利智能体系统",
    "type": "team",
    "children": [
      {
        "id": "group-1",
        "name": "统筹管理层",
        "type": "group",
        "children": [
          {
            "id": "agent-1",
            "name": "CEO Agent",
            "type": "agent",
            "agent_config": {},
            "children": []
          }
        ]
      }
    ]
  }
}
```

### 7.2 更新组织架构树

```http
PUT /api/v1/organization/tree
Authorization: Bearer {token}

{
  "id": "root",
  "name": "新名称",
  "children": [...]
}
```

### 7.3 添加节点

```http
POST /api/v1/organization/nodes
Authorization: Bearer {token}

{
  "parent_id": "parent-uuid",
  "name": "新节点",
  "type": "group",
  "description": "节点描述"
}
```

### 7.4 更新节点

```http
PUT /api/v1/organization/nodes/{id}
Authorization: Bearer {token}

{
  "name": "更新后的名称",
  "description": "更新后的描述"
}
```

### 7.5 移动节点

```http
POST /api/v1/organization/nodes/{id}/move
Authorization: Bearer {token}

{
  "new_parent_id": "new-parent-uuid",
  "position": 2
}
```

### 7.6 删除节点

```http
DELETE /api/v1/organization/nodes/{id}
Authorization: Bearer {token}
```

---

## 8. 专利文档接口

### 8.1 获取专利文档

```http
GET /api/v1/patents/{task_id}/document
Authorization: Bearer {token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "title": "专利标题",
    "abstract": "摘要...",
    "claims": {},
    "description": {},
    "drawings": [],
    "version": 2,
    "created_at": "2024-01-20T10:00:00Z"
  }
}
```

### 8.2 下载专利文档

```http
GET /api/v1/patents/{task_id}/download?format=docx
Authorization: Bearer {token}
```

**支持格式**:
- `docx`: Word 文档
- `pdf`: PDF 文档
- `json`: JSON 格式
- `md`: Markdown 格式

### 8.3 获取文档版本历史

```http
GET /api/v1/patents/{task_id}/versions
Authorization: Bearer {token}
```

### 8.4 获取特定版本文档

```http
GET /api/v1/patents/{task_id}/versions/{version}
Authorization: Bearer {token}
```

### 8.5 生成新的文档版本

```http
POST /api/v1/patents/{task_id}/regenerate
Authorization: Bearer {token}

{
  "regenerate_claims": true,
  "regenerate_description": false,
  "instructions": "修改权利要求的描述方式"
}
```

---

## 9. 专利检索接口

### 9.1 检索现有技术专利

```http
POST /api/v1/search/patents
Authorization: Bearer {token}

{
  "query": "人工智能 多智能体 专利申请",
  "sources": ["cnipa", "uspto", "epo"],
  "limit": 20,
  "filters": {
    "start_date": "2020-01-01",
    "end_date": "2024-12-31",
    "ipc_codes": ["G06N", "G06F"]
  }
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "query": "人工智能 多智能体 专利申请",
    "total": 156,
    "search_time_ms": 2345,
    "results": [
      {
        "patent_number": "CN112345678A",
        "title": "基于多智能体的专利申请系统",
        "abstract": "本发明公开了一种...",
        "applicant": "某某公司",
        "publication_date": "2021-01-01",
        "similarity_score": 0.87,
        "source": "cnipa"
      }
    ]
  }
}
```

### 9.2 检索知识库

```http
GET /api/v1/search/knowledge?query=关键词&top_k=10
Authorization: Bearer {token}
```

### 9.3 专利相似度对比

```http
POST /api/v1/search/similarity
Authorization: Bearer {token}

{
  "target_patent_id": "patent-uuid",
  "compare_with": ["patent-1", "patent-2"]
}
```

---

## 10. 系统统计接口

### 10.1 获取仪表盘数据

```http
GET /api/v1/stats/dashboard
Authorization: Bearer {token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "total_tasks": 120,
    "completed_tasks": 85,
    "in_progress_tasks": 32,
    "failed_tasks": 3,
    "success_rate": 96.59,
    "avg_completion_time_hours": 2.5,
    "active_agents": 5,
    "total_tokens_used": 1250000,
    "estimated_cost_usd": 15.50,
    "trends": {
      "tasks_last_7_days": [12, 15, 8, 20, 15, 18, 12],
      "success_rate_last_7_days": [95, 98, 92, 97, 96, 99, 95]
    }
  }
}
```

### 10.2 获取系统状态

```http
GET /api/v1/system/status
Authorization: Bearer {token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 86400,
    "database": "connected",
    "redis": "connected",
    "llm_api": "connected",
    "patent_api": "connected",
    "active_workers": 8,
    "queued_tasks": 3,
    "agents": [
      {
        "name": "CEO Agent",
        "status": "idle",
        "current_task": null
      }
    ]
  }
}
```

### 10.3 获取使用统计

```http
GET /api/v1/stats/usage?start_date=2024-01-01&end_date=2024-01-31
Authorization: Bearer {token}
```

---

## 附录

### A. Webhook 事件

系统支持通过 Webhook 推送事件通知:

| 事件类型 | 说明 |
|---------|------|
| task.created | 任务创建 |
| task.state_changed | 任务状态变更 |
| task.completed | 任务完成 |
| task.failed | 任务失败 |
| agent.output | Agent 产生输出 |
| chat.message_received | 收到新消息 |

**Webhook 签名验证**:
```
X-Webhook-Signature: sha256={signature}
```

### B. 限流策略

| 级别 | 限制 |
|------|------|
| 免费用户 | 100 次/天, 5 次/分钟 |
| 专业用户 | 1000 次/天, 60 次/分钟 |
| 企业用户 | 不限量, 可协商 |

---

**文档版本**: v1.0
**最后更新**: 2024-01-20
