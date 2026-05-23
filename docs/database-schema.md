# 数据库设计文档

**版本**: v1.0
**数据库**: PostgreSQL 15+

---

## 目录

1. [数据库设计原则](#1-数据库设计原则)
2. [ER 关系图](#2-er-关系图)
3. [表结构详情](#3-表结构详情)
4. [索引设计](#4-索引设计)
5. [分区策略](#5-分区策略)
6. [数据迁移计划](#6-数据迁移计划)

---

## 1. 数据库设计原则

### 1.1 命名规范

- 表名: 小写 + 下划线分隔，复数形式 (如 `patent_tasks`)
- 列名: 小写 + 下划线分隔 (如 `created_at`)
- 外键: `{表名}_id` 格式
- 索引: `idx_{表名}_{列名}`
- 唯一约束: `uc_{表名}_{列名}`

### 1.2 通用字段

所有业务表都包含以下字段:

```sql
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
created_by UUID REFERENCES users(id),
is_deleted BOOLEAN NOT NULL DEFAULT FALSE
```

### 1.3 软删除策略

所有表使用软删除 (`is_deleted`)，查询时默认过滤已删除数据。

---

## 2. ER 关系图

```
┌─────────────┐
│   users     │
├─────────────┤
│ id (PK)     │
│ email       │ ◄──┐
│ name        │    │
│ password    │    │
│ role        │    │
│ avatar_url  │    │
│ is_active   │    │
│ created_at  │    │
│ updated_at  │    │
│ last_login  │    │
└─────────────┘    │
       │           │
       │ 1:N       │
       ▼           │
┌─────────────────────────────┐      ┌───────────────────┐
│      patent_tasks           │      │   organizations   │
├─────────────────────────────┤      ├───────────────────┤
│ id (PK)                     │◄──┐  │ id (PK)           │
│ user_id (FK) → users.id    │   │  │ name              │
│ org_id (FK) → org.id        │───┘  │ slug              │
│ title                       │      │ settings JSON     │
│ tech_description TEXT       │      │ created_at        │
│ patent_type VARCHAR(32)     │      └───────────────────┘
│ current_state VARCHAR(32)   │           │
│ progress INT                │           │ 1:N
│ iteration_count INT         │           ▼
│ error_message TEXT          │  ┌───────────────────┐
│ metadata JSONB              │  │  org_members      │
│ started_at TIMESTAMPTZ      │  ├───────────────────┤
│ completed_at TIMESTAMPTZ    │  │ id (PK)           │
│ created_at                  │  │ org_id (FK)       │
│ updated_at                  │  │ user_id (FK)      │
└─────────────────────────────┘  │ role              │
       │    │    │    │           │ joined_at         │
       │    │    │    │           └───────────────────┘
       │    │    │    │
  1:1  │    │    │    │
┌──────┴────┴────┴──────────────────────────────┐
│           专利产出表 (一对一)                  │
├─────────────────┬─────────────────────────────┤
│ requirement_docs│  retrieval_reports          │
│ patent_drafts   │  review_reports              │
│ final_patents   │  task_events                 │
└─────────────────┴─────────────────────────────┘

┌─────────────────────────────────────┐
│               agents                │
├─────────────────────────────────────┤
│ id (PK)                             │
│ name                                │
│ description                         │
│ type VARCHAR(32)                   │
│ role VARCHAR(32)                   │
│ is_enabled BOOLEAN                  │
│ config JSONB                        │
│ system_prompt TEXT                  │
│ model VARCHAR(64)                   │
│ temperature FLOAT                   │
│ max_tokens INT                      │
│ parent_id (FK) → agents.id         │
│ organization_id (FK)               │
│ created_at                          │
│ updated_at                          │
└─────────────────────────────────────┘
           │
           │ 1:N
           ▼
┌─────────────────────────────────────┐
│            agent_tools             │
├─────────────────────────────────────┤
│ id (PK)                             │
│ agent_id (FK) → agents.id          │
│ name                                │
│ description                         │
│ tool_type VARCHAR(32)              │
│ config JSONB                        │
│ is_enabled BOOLEAN                  │
│ created_at                          │
└─────────────────────────────────────┘
```

---

## 3. 表结构详情

### 3.1 用户与组织

#### 3.1.1 `users` - 用户表

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(512),
    role VARCHAR(32) NOT NULL DEFAULT 'user', -- user, admin, org_admin
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    last_login TIMESTAMPTZ,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

#### 3.1.2 `organizations` - 组织表

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    logo_url VARCHAR(512),
    description TEXT,
    settings JSONB DEFAULT '{}',
    plan_type VARCHAR(32) DEFAULT 'free', -- free, pro, enterprise
    quota JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
```

#### 3.1.3 `organization_members` - 组织成员

```sql
CREATE TABLE organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(32) NOT NULL DEFAULT 'member', -- owner, admin, member, viewer
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invited_by UUID REFERENCES users(id),
    UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_org_members_user ON organization_members(user_id);
CREATE INDEX idx_org_members_org ON organization_members(organization_id);
```

### 3.2 专利任务与工作流

#### 3.2.1 `patent_tasks` - 专利任务主表

```sql
CREATE TABLE patent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    title VARCHAR(500) NOT NULL,
    tech_description TEXT NOT NULL,
    patent_type VARCHAR(32) NOT NULL DEFAULT 'invention', -- invention, utility, design
    current_state VARCHAR(32) NOT NULL DEFAULT 'initial', -- 工作流状态
    progress SMALLINT NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    iteration_count INT NOT NULL DEFAULT 0,
    priority VARCHAR(16) DEFAULT 'normal', -- low, normal, high, urgent
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_patent_tasks_user ON patent_tasks(user_id);
CREATE INDEX idx_patent_tasks_state ON patent_tasks(current_state);
CREATE INDEX idx_patent_tasks_created ON patent_tasks(created_at DESC);
CREATE INDEX idx_patent_tasks_org ON patent_tasks(organization_id);
CREATE INDEX idx_patent_tasks_priority ON patent_tasks(priority);
```

#### 3.2.2 `task_events` - 任务事件日志

```sql
CREATE TABLE task_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES patent_tasks(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL, -- state_change, agent_start, message, etc.
    agent_name VARCHAR(100),
    title VARCHAR(255),
    description TEXT,
    data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_task_events_task ON task_events(task_id, created_at DESC);
CREATE INDEX idx_task_events_type ON task_events(event_type);
```

### 3.3 专利产出文档

#### 3.3.1 `requirement_docs` - 需求分析文档

```sql
CREATE TABLE requirement_docs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL UNIQUE REFERENCES patent_tasks(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    tech_field VARCHAR(200),
    core_principle TEXT,
    technical_problem TEXT,
    application_scenarios JSONB DEFAULT '[]', -- 应用场景列表
    key_features JSONB DEFAULT '[]', -- 核心创新点
    patent_type_recommendation JSONB, -- 专利类型建议
    beneficial_effects JSONB DEFAULT '[]', -- 有益效果
    information_gaps JSONB DEFAULT '[]', -- 信息缺口
    raw_output TEXT, -- 原始 LLM 输出
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 3.3.2 `retrieval_reports` - 检索分析报告

```sql
CREATE TABLE retrieval_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL UNIQUE REFERENCES patent_tasks(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    novelty_assessment JSONB NOT NULL, -- 新颖性评估
    inventive_step_assessment JSONB NOT NULL, -- 创造性评估
    utility_assessment JSONB NOT NULL, -- 实用性评估
    similar_patents JSONB DEFAULT '[]', -- 相似专利列表
    writing_recommendations JSONB DEFAULT '[]', -- 撰写建议
    overall_patentability VARCHAR(16) DEFAULT 'medium', -- low, medium, high
    overall_score NUMERIC(4,2), -- 0-100
    risk_factors JSONB DEFAULT '[]', -- 风险因素
    search_criteria JSONB, -- 检索条件
    data_sources JSONB DEFAULT '[]', -- 检索数据源
    raw_output TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 3.3.3 `patent_drafts` - 专利草案

```sql
CREATE TABLE patent_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL UNIQUE REFERENCES patent_tasks(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    claims JSONB NOT NULL, -- 权利要求 {independent, dependent[]}
    description JSONB NOT NULL, -- 说明书各部分
    abstract TEXT, -- 摘要
    technical_field TEXT, -- 技术领域
    background_art TEXT, -- 背景技术
    summary TEXT, -- 发明内容
    description_drawings TEXT, -- 附图说明
    detailed_description TEXT, -- 具体实施方式
    drawings JSONB DEFAULT '[]', -- 附图
    key_terms JSONB DEFAULT '{}', -- 术语表
    raw_output TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 3.3.4 `review_reports` - 质量审查报告

```sql
CREATE TABLE review_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL UNIQUE REFERENCES patent_tasks(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    formal_compliance JSONB NOT NULL, -- 形式合规性
    claims_review JSONB NOT NULL, -- 权利要求审查
    description_review JSONB NOT NULL, -- 说明书审查
    consistency_review JSONB NOT NULL, -- 一致性审查
    examination_risks JSONB DEFAULT '[]', -- 审查风险
    overall_score NUMERIC(4,2), -- 总体得分
    recommendation VARCHAR(16) NOT NULL, -- approve, revise, reject
    revision_priority VARCHAR(16), -- critical, high, medium, low
    issues JSONB DEFAULT '[]', -- 问题列表
    suggestions JSONB DEFAULT '[]', -- 修改建议
    raw_output TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 3.3.5 `final_patents` - 最终专利文档

```sql
CREATE TABLE final_patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL UNIQUE REFERENCES patent_tasks(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    title VARCHAR(500) NOT NULL,
    abstract TEXT,
    claims JSONB NOT NULL,
    description JSONB NOT NULL,
    drawings JSONB DEFAULT '[]',
    file_urls JSONB DEFAULT '{}', -- 各格式文件 URL
    format_versions JSONB DEFAULT '[]', -- 格式版本历史
    submitted_at TIMESTAMPTZ,
    submission_reference VARCHAR(255), -- 提交参考号
    status VARCHAR(32) DEFAULT 'generated', -- generated, submitted, pending_review
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.4 聊天与会话

#### 3.4.1 `chat_sessions` - 聊天会话

```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    task_id UUID REFERENCES patent_tasks(id),
    title VARCHAR(500),
    session_type VARCHAR(32) DEFAULT 'general', -- brainstorm, task, support
    metadata JSONB DEFAULT '{}',
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id, last_message_at DESC);
CREATE INDEX idx_chat_sessions_task ON chat_sessions(task_id);
```

#### 3.4.2 `chat_messages` - 聊天消息

```sql
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    task_id UUID REFERENCES patent_tasks(id),
    role VARCHAR(32) NOT NULL, -- user, assistant, system, agent
    agent_name VARCHAR(100), -- 如果是 Agent 消息
    content TEXT NOT NULL,
    message_type VARCHAR(32) DEFAULT 'text', -- text, json, file, progress
    metadata JSONB DEFAULT '{}',
    tokens_used INT, -- Token 消耗
    latency_ms INT, -- 响应延迟
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX idx_chat_messages_task ON chat_messages(task_id);
```

### 3.5 Agent 管理

#### 3.5.1 `agents` - Agent 配置

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    parent_id UUID REFERENCES agents(id), -- 父 Agent
    name VARCHAR(100) NOT NULL,
    description TEXT,
    agent_type VARCHAR(32) NOT NULL, -- orchestrator, specialist, assistant
    role VARCHAR(64) NOT NULL,
    system_prompt TEXT NOT NULL,
    model VARCHAR(64) NOT NULL DEFAULT 'gpt-4-turbo',
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.7,
    max_tokens INT NOT NULL DEFAULT 2048,
    top_p NUMERIC(3,2) DEFAULT 1.0,
    frequency_penalty NUMERIC(3,2) DEFAULT 0,
    presence_penalty NUMERIC(3,2) DEFAULT 0,
    working_directory VARCHAR(512),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_template BOOLEAN NOT NULL DEFAULT FALSE, -- 是否为模板
    config JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(organization_id, name)
);

CREATE INDEX idx_agents_type ON agents(agent_type);
CREATE INDEX idx_agents_parent ON agents(parent_id);
```

#### 3.5.2 `agent_tools` - Agent 工具

```sql
CREATE TABLE agent_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    tool_type VARCHAR(32) NOT NULL, -- search, file, analysis, external, api
    schema_json JSONB, -- 工具定义
    config JSONB DEFAULT '{}',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    execution_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id, name)
);
```

#### 3.5.3 `agent_skills` - Agent 技能

```sql
CREATE TABLE agent_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    skill_type VARCHAR(32),
    version VARCHAR(32) DEFAULT '1.0.0',
    prompt_template TEXT,
    examples JSONB DEFAULT '[]',
    config JSONB DEFAULT '{}',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id, name)
);
```

#### 3.5.4 `agent_memories` - Agent 记忆

```sql
CREATE TABLE agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    memory_type VARCHAR(32) NOT NULL, -- short_term, long_term, knowledge
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536), -- OpenAI ada-002 向量
    metadata JSONB DEFAULT '{}',
    importance_score NUMERIC(3,2) DEFAULT 0.5, -- 0-1 重要度
    access_count INT NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_memories_agent ON agent_memories(agent_id);
CREATE INDEX idx_agent_memories_type ON agent_memories(memory_type);
CREATE INDEX idx_agent_memories_embedding ON agent_memories USING hnsw (embedding vector_cosine_ops);
```

### 3.6 文件存储

#### 3.6.1 `documents` - 文档存储

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES patent_tasks(id),
    user_id UUID REFERENCES users(id),
    doc_type VARCHAR(32) NOT NULL, -- requirement, retrieval, draft, review, final
    file_name VARCHAR(512) NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    file_size BIGINT NOT NULL, -- bytes
    file_format VARCHAR(32) NOT NULL, -- docx, pdf, json, md
    mime_type VARCHAR(100),
    version INT NOT NULL DEFAULT 1,
    is_latest BOOLEAN NOT NULL DEFAULT TRUE,
    md5_hash CHAR(32),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_documents_task ON documents(task_id);
CREATE INDEX idx_documents_type ON documents(doc_type);
```

### 3.7 知识库

#### 3.7.1 `knowledge_patents` - 专利知识库

```sql
CREATE TABLE knowledge_patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patent_number VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(1000) NOT NULL,
    abstract TEXT,
    application_number VARCHAR(64),
    publication_number VARCHAR(64),
    applicant VARCHAR(500),
    inventor VARCHAR(500),
    application_date DATE,
    publication_date DATE,
    ipc_codes TEXT[] DEFAULT '{}', -- IPC 分类号
    cpc_codes TEXT[] DEFAULT '{}', -- CPC 分类号
    country_code VARCHAR(8), -- CN, US, EP, etc.
    status VARCHAR(32),
    abstract_embedding vector(1536),
    full_text_embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    source VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_kp_number ON knowledge_patents(patent_number);
CREATE INDEX idx_kp_ipc ON knowledge_patents USING GIN(ipc_codes);
CREATE INDEX idx_kp_abstract_vec ON knowledge_patents USING hnsw (abstract_embedding vector_cosine_ops);
```

### 3.8 审计与日志

#### 3.8.1 `audit_logs` - 审计日志

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64),
    resource_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
```

#### 3.8.2 `api_usage` - API 使用统计

```sql
CREATE TABLE api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    api_endpoint VARCHAR(255),
    method VARCHAR(16),
    status_code INT,
    response_time_ms INT,
    tokens_used INT,
    cost_amount NUMERIC(10,4),
    cost_currency VARCHAR(8) DEFAULT 'USD',
    user_agent VARCHAR(512),
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_api_usage_user ON api_usage(user_id, created_at DESC);
CREATE INDEX idx_api_usage_org ON api_usage(organization_id, created_at DESC);
CREATE INDEX idx_api_usage_date ON api_usage(created_at);
```

---

## 4. 索引设计

### 4.1 主键索引

所有表的 `id` 列自动创建 B 树索引。

### 4.2 外键索引

所有外键列自动创建索引，提升 JOIN 查询性能。

### 4.3 业务索引

| 表名 | 索引列 | 类型 | 用途 |
|------|--------|------|------|
| patent_tasks | (user_id, created_at DESC) | B-tree | 用户任务查询 |
| patent_tasks | (current_state, created_at) | B-tree | 状态筛选 |
| task_events | (task_id, created_at DESC) | B-tree | 任务事件流 |
| chat_messages | (session_id, created_at) | B-tree | 聊天历史 |
| agent_memories | (embedding) | HNSW | 向量相似度搜索 |
| knowledge_patents | (abstract_embedding) | HNSW | 专利相似度检索 |

### 4.4 全文搜索索引

```sql
-- 专利标题和摘要全文搜索
CREATE INDEX idx_patent_search ON knowledge_patents 
USING GIN (to_tsvector('english', title || ' ' || COALESCE(abstract, '')));
```

---

## 5. 分区策略

### 5.1 按时间分区

对于大表按月份分区:

- `task_events`
- `chat_messages`
- `audit_logs`
- `api_usage`

### 5.2 按组织分区

对于多租户表按组织 ID 分区:

- `patent_tasks`
- `agents`

---

## 6. 数据迁移计划

### 6.1 初始迁移 (v1)

1. 创建基础表结构
2. 创建索引与约束
3. 插入种子数据 (默认 Agent 配置、系统用户等)

### 6.2 后续版本迁移

每个数据结构变更通过独立的 Alembic 迁移脚本管理。

---

**文档版本**: v1.0
**最后更新**: 2024-01-20
