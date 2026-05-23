# 分阶段执行计划

**总周期**: 15 周 (约 3.5 个月)
**总工时估算**: ~585 小时

---

## 目录

1. [Phase 1: 后端核心基础设施 (第 1-2 周)](#phase-1-后端核心基础设施-第-1-2-周)
2. [Phase 2: 数据层与持久化 (第 2-3 周)](#phase-2-数据层与持久化-第-2-3-周)
3. [Phase 3: Agent 智能体核心 (第 3-5 周)](#phase-3-agent-智能体核心-第-3-5-周)
4. [Phase 4: API 服务层 (第 6-7 周)](#phase-4-api-服务层-第-6-7-周)
5. [Phase 5: 前端数据集成 (第 8-10 周)](#phase-5-前端数据集成-第-8-10-周)
6. [Phase 6: 第三方集成 (第 11-12 周)](#phase-6-第三方集成-第-11-12-周)
7. [Phase 7: 测试与优化 (第 13-15 周)](#phase-7-测试与优化-第-13-15-周)
8. [里程碑验收标准](#里程碑验收标准)

---

## Phase 1: 后端核心基础设施 (第 1-2 周)

**预计工时**: 35 小时
**目标**: 建立完整的后端基础设施

### 任务清单

#### 1.1 项目配置系统 (4h) ✅
- [x] 使用 Pydantic Settings 实现配置管理
- [x] 支持多环境配置 (dev/staging/prod)
- [x] 环境变量覆盖
- [x] 配置类型验证

**交付文件**:
- `backend/src/core/config.py`
- `backend/.env.example`

#### 1.2 日志系统 (3h) ✅
- [x] Structlog 结构化日志集成
- [x] 日志分级 (DEBUG/INFO/WARNING/ERROR)
- [x] 请求 ID 追踪
- [x] 日志格式化与输出配置
- [x] 敏感信息自动审查屏蔽

**交付文件**:
- `backend/src/core/logging.py`

#### 1.3 异常处理与错误码 (4h) ✅
- [x] 自定义异常基类
- [x] 18+ 业务异常定义
- [x] FastAPI 全局异常处理器
- [x] 错误码枚举与严重级别
- [x] 统一错误响应格式

**交付文件**:
- `backend/src/core/exceptions.py`

#### 1.4 依赖注入容器 (4h) ✅
- [x] Dependency Injector 集成
- [x] 数据库/Redis/LLM Provider 定义
- [x] 服务生命周期管理
- [x] 容器启动/清理钩子

**交付文件**:
- `backend/src/core/container.py`

#### 1.5 中间件 (5h) ✅
- [x] CORS 中间件
- [x] JWT 认证中间件与权限装饰器
- [x] SlowAPI 请求限流中间件
- [x] 请求日志中间件
- [x] 请求 ID 中间件
- [x] SSE 连接管理器

**交付文件**:
- `backend/src/core/middleware.py`

**交付文件**:
- `backend/src/core/middleware.py`

#### 1.7 事件总线 (4h) ✅
- [x] 事件基类定义 (BaseEvent)
- [x] 事件类型枚举 (EventType)
- [x] 内存事件总线实现 (pub/sub)
- [x] Redis 事件总线（分布式）
- [x] 任务进度/Agent 思考/聊天消息等预定义事件
- [x] SSE 前端实时推送集成

**交付文件**:
- `backend/src/core/events.py`

#### 1.8 任务队列 (Celery + Redis) (6h) ✅
- [x] Celery 集成与配置
- [x] 优雅降级（无 Broker 时同步执行）
- [x] 工作流异步任务定义
- [x] Agent 任务定义
- [x] 本地任务执行器（开发环境）
- [x] 定时任务配置（清理、健康检查）

**交付文件**:
- `backend/src/core/tasks.py`

#### 1.9 基础工具类 (3h)
- [ ] 加密工具 (密码哈希、JWT)
- [ ] 验证工具 (邮箱、手机号等)
- [ ] 日期时间工具
- [ ] 字符串处理工具

**交付文件**:
- `backend/src/utils/`

---

## Phase 2: 数据层与持久化 (第 2-3 周)

**预计工时**: 54 小时
**目标**: 实现完整的数据访问层

### 任务清单

#### 2.1 数据库设计 (8h)
- [ ] 完整 ER 图设计
- [ ] 表结构定义 (20+ 表)
- [ ] 索引策略设计
- [ ] 外键与约束定义
- [ ] 分区策略设计

**交付文件**:
- `docs/database-schema.md` (已创建)

#### 2.2 SQLAlchemy 模型定义 (10h)
- [ ] 用户与组织模型
- [ ] 专利任务模型
- [ ] 专利产出文档模型
- [ ] Agent 管理模型
- [ ] 聊天与会话模型
- [ ] 文件存储模型
- [ ] 知识库模型
- [ ] 审计日志模型

**交付文件**:
- `backend/src/models/`

#### 2.3 Alembic 迁移脚本 (4h)
- [ ] 初始迁移脚本
- [ ] 种子数据迁移
- [ ] 索引创建脚本
- [ ] 版本化管理

**交付文件**:
- `backend/alembic/`

#### 2.4 Repository 模式 (12h)
为每个主要实体实现 Repository:
- [ ] 用户 Repository
- [ ] 任务 Repository
- [ ] 专利文档 Repository
- [ ] Agent Repository
- [ ] 聊天 Repository
- [ ] 基础 CRUD 基类
- [ ] 分页与排序支持
- [ ] 软删除支持

**交付文件**:
- `backend/src/data/repositories/`

#### 2.5 Unit of Work 模式 (4h)
- [ ] UoW 接口定义
- [ ] SQLAlchemy 实现
- [ ] 事务管理
- [ ] 多 Repository 协调

**交付文件**:
- `backend/src/data/unit_of_work.py`

#### 2.6 Redis 缓存集成 (6h)
- [ ] 缓存抽象层
- [ ] Redis 客户端配置
- [ ] 缓存策略实现 (TTL、LRU)
- [ ] 缓存预热/失效机制
- [ ] 分布式锁支持

**交付文件**:
- `backend/src/core/cache.py`

#### 2.7 MinIO 对象存储集成 (6h)
- [ ] MinIO 客户端配置
- [ ] 文件上传/下载接口
- [ ] 文件元数据管理
- [ ] 预签名 URL 生成
- [ ] 文件版本管理

**交付文件**:
- `backend/src/core/storage.py`

#### 2.8 数据库种子数据 (4h)
- [ ] 默认 Agent 配置
- [ ] 系统用户创建
- [ ] 默认组织创建
- [ ] 测试数据生成

**交付文件**:
- `backend/src/data/seed.py`

---

## Phase 3: Agent 智能体核心 (第 3-5 周)

**预计工时**: 146 小时
**目标**: 实现完整的多 Agent 系统

### 任务清单

#### 3.1 LLM 集成层 (8h)
- [ ] OpenAI API 集成
- [ ] Claude API 集成
- [ ] 统一 LLM 接口抽象
- [ ] Token 计数与成本统计
- [ ] 错误重试与降级策略
- [ ] 请求限流与并发控制

**交付文件**:
- `backend/src/agents/llm_client.py`

#### 3.2 Prompt 模板引擎 (6h)
- [ ] Jinja2 模板集成
- [ ] Prompt 版本管理
- [ ] 动态变量注入
- [ ] 示例 Few-Shot 管理
- [ ] Prompt 效果评估框架

**交付文件**:
- `backend/src/prompts/`

#### 3.3 Hermes Agent 底座集成 (12h)
基于 NousResearch Hermes Agent 架构，实现完整的 Agent 运行时

- [x] Hermes Agent 基类实现
  - [x] 系统提示词管理
  - [x] 思考-行动（ReAct）循环实现
  - [x] 函数调用解析与执行
  - [x] 结构化输出解析（JSON Schema）
  - [x] 思考过程追踪
- [x] 工具系统
  - [x] 工具定义 Schema（HermesToolDefinition）
  - [x] 工具注册与发现机制
  - [x] 工具执行与错误处理
  - [x] 工具结果格式化
- [x] 子 Agent 孵化能力
  - [x] Agent.spawn_child_agent() 接口
  - [x] 父子 Agent 上下文传递
  - [x] 子 Agent 生命周期管理
- [x] Agent 协调器（CEO 模式）
  - [x] 多 Agent 工作流编排
  - [x] 结果聚合与传递
  - [x] 错误降级与重试
- [x] 消息协议
  - [x] HermesMessage 统一消息格式
  - [x] OpenAI 格式转换
  - [x] 函数调用/结果消息类型

**交付文件**:
- `backend/src/agents/hermes/base.py` (Hermes Agent 核心实现)
- `backend/src/agents/hermes/tools/` (通用工具目录)
- `backend/src/agents/hermes/memory.py` (记忆系统)

#### 3.4 记忆系统 (8h)
- [ ] 短期记忆（对话历史）
- [ ] 长期记忆（向量存储）
- [ ] 知识库记忆检索
- [ ] 记忆重要度评分
- [ ] 记忆过期清理策略

**交付文件**:
- `backend/src/agents/hermes/memory.py`

#### 3.5 专业工具开发 (10h)
基于 Hermes Tool 基类，实现专利申请专用工具集

- [ ] 专利检索工具
  - 多数据源支持（Google Patents, WIPO, CNIPA）
  - 相似度比对算法
  - 引用关系分析
- [ ] 知识库搜索工具
  - 向量相似度检索
  - 专利法知识库
  - 审查规则库
- [ ] 文档生成工具
  - Markdown/Word/PDF 导出
  - 专利格式规范化
  - 目录生成
- [ ] 技术术语工具
  - IPC 分类查询
  - 术语标准化
  - 中英文对照

**交付文件**:
- `backend/src/agents/hermes/tools/patent_search.py`
- `backend/src/agents/hermes/tools/kb_search.py`
- `backend/src/agents/hermes/tools/doc_generator.py`
- `backend/src/agents/hermes/tools/term_normalizer.py`

#### 3.6 Prompt 模板引擎 (6h)
- [ ] Jinja2 模板集成
- [ ] Prompt 版本管理
- [ ] 动态变量注入
- [ ] Few-Shot 示例管理
- [ ] Prompt 效果评估

**交付文件**:
- `backend/src/prompts/`

#### 3.7 需求分析 Agent (16h)
- [ ] 技术领域识别
- [ ] 创新点提取
- [ ] 技术问题分析
- [ ] 专利类型建议
- [ ] 应用场景挖掘
- [ ] 信息缺口识别
- [ ] 需求文档生成
- [ ] 单元测试

**交付文件**:
- `backend/src/agents/requirement_analyst.py`

#### 3.7 检索分析 Agent (16h)
- [ ] 检索关键词生成
- [ ] 多数据源检索协调
- [ ] 新颖性评估
- [ ] 创造性评估
- [ ] 实用性评估
- [ ] 相似专利对比
- [ ] 风险因素识别
- [ ] 撰写建议生成
- [ ] 检索报告生成
- [ ] 单元测试

**交付文件**:
- `backend/src/agents/retrieval_analyst.py`

#### 3.8 专利撰写 Agent (20h)
- [ ] 权利要求书撰写
- [ ] 说明书各部分撰写
- [ ] 技术术语统一
- [ ] 专利格式合规
- [ ] 支持多轮修改
- [ ] 版本对比
- [ ] 草稿生成
- [ ] 单元测试

**交付文件**:
- `backend/src/agents/patent_writer.py`

#### 3.9 质量审查 Agent (16h)
- [ ] 形式合规审查
- [ ] 权利要求审查
- [ ] 说明书审查
- [ ] 一致性检查
- [ ] 审查风险预判
- [ ] 问题分级 (高/中/低)
- [ ] 修改建议生成
- [ ] 审查报告输出
- [ ] 单元测试

**交付文件**:
- `backend/src/agents/quality_reviewer.py`

#### 3.10 CEO 调度 Agent (20h)
- [ ] 工作流状态机
- [ ] Agent 任务分配
- [ ] 质量门控检查
- [ ] 迭代决策逻辑
- [ ] 异常处理与回滚
- [ ] 进度报告生成
- [ ] 跨 Agent 信息同步
- [ ] 资源协调与负载均衡
- [ ] 单元测试

**交付文件**:
- `backend/src/agents/ceo.py`

#### 3.11 Agent 间通信协议 (8h)
- [ ] 消息格式定义
- [ ] 消息队列实现
- [ ] 消息确认机制
- [ ] 消息持久化
- [ ] 死信队列处理

**交付文件**:
- `backend/src/agents/messaging.py`

#### 3.12 任务调度与队列管理 (8h)
- [ ] 任务队列优先级
- [ ] 任务超时处理
- [ ] 工作线程池管理
- [ ] 任务状态持久化
- [ ] 失败任务重试

**交付文件**:
- `backend/src/core/task_scheduler.py`

---

## Phase 4: API 服务层 (第 6-7 周)

**预计工时**: 98 小时
**目标**: 实现完整的 REST API + SSE 实时通信

### 任务清单

#### 4.1 JWT 认证与授权系统 (8h)
- [ ] 用户登录/注册
- [ ] Token 签发与刷新
- [ ] 权限装饰器
- [ ] 角色权限矩阵
- [ ] Token 黑名单
- [ ] OAuth2 集成 (可选)

**交付文件**:
- `backend/src/api/dependencies/auth.py`

#### 4.2 用户与组织管理 API (12h)
- [ ] 用户 CRUD
- [ ] 组织 CRUD
- [ ] 成员管理
- [ ] 权限变更
- [ ] 邀请机制
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/users.py`
- `backend/src/api/routes/organizations.py`

#### 4.3 专利任务 CRUD API (8h)
- [ ] 创建任务
- [ ] 任务列表/筛选/搜索
- [ ] 任务详情
- [ ] 任务取消/删除
- [ ] 任务优先级调整
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/tasks.py`

#### 4.4 聊天对话 API (8h)
- [ ] 发送消息
- [ ] 消息历史
- [ ] 会话管理
- [ ] 消息编辑/删除
- [ ] 消息搜索
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/chat.py`

#### 4.5 SSE 实时事件流 API (8h)
- [ ] SSE 服务端实现
- [ ] 事件类型定义
- [ ] 客户端连接管理
- [ ] 断线重连支持
- [ ] 事件推送性能优化
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/events.py`

#### 4.6 Agent 管理 API (12h)
- [ ] Agent CRUD
- [ ] 配置更新
- [ ] 工具管理
- [ ] 技能管理
- [ ] 记忆管理
- [ ] 启用/禁用
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/agents.py`

#### 4.7 组织架构 API (8h)
- [ ] 树结构获取
- [ ] 节点增删改
- [ ] 节点移动
- [ ] 批量操作
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/organization_tree.py`

#### 4.8 专利检索 API (10h)
- [ ] 现有技术检索
- [ ] 知识库检索
- [ ] 相似度对比
- [ ] 检索历史
- [ ] 检索结果导出
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/search.py`

#### 4.9 专利文档 API (8h)
- [ ] 文档获取
- [ ] 文档下载 (多格式)
- [ ] 版本历史
- [ ] 文档再生
- [ ] 在线编辑
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/documents.py`

#### 4.10 系统统计与仪表盘 API (6h)
- [ ] 仪表盘数据
- [ ] 使用统计
- [ ] 系统状态
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/stats.py`

#### 4.11 Webhook 回调系统 (6h)
- [ ] Webhook 注册
- [ ] 事件订阅
- [ ] 签名验证
- [ ] 重试机制
- [ ] 事件日志
- [ ] API 测试

**交付文件**:
- `backend/src/api/routes/webhooks.py`

#### 4.12 API 限流与防刷 (4h)
- [ ] 限流策略实现
- [ ] 用户级别限流
- [ ] IP 级别限流
- [ ] 限流响应处理

---

## Phase 5: 前端数据集成 (第 8-10 周)

**预计工时**: 138 小时
**目标**: 前端接入真实 API，完整功能实现

### 任务清单

#### 5.1 状态管理重构 (Zustand) (12h)
- [ ] Auth Store
- [ ] Chat Store
- [ ] Task Store
- [ ] Agent Store
- [ ] UI State Store
- [ ] 持久化插件

**交付文件**:
- `frontend/lib/store/`

#### 5.2 React Query 数据缓存层 (16h)
- [ ] Query Client 配置
- [ ] Query Key 管理
- [ ] 乐观更新配置
- [ ] 缓存失效策略
- [ ] 后台刷新
- [ ] 分页/无限滚动封装

**交付文件**:
- `frontend/lib/react-query/`

#### 5.3 API 客户端层完善 (8h)
- [ ] HTTP 客户端封装
- [ ] 认证 Token 管理
- [ ] 请求/响应拦截器
- [ ] 错误统一处理
- [ ] 请求重试机制
- [ ] TypeScript 类型定义

**交付文件**:
- `frontend/lib/api/`

#### 5.4 首页/聊天页面数据集成 (12h)
- [ ] 真实消息发送
- [ ] SSE 事件流接入
- [ ] 头脑风暴阶段逻辑
- [ ] 方案确认与启动流程
- [ ] 历史消息加载
- [ ] 加载/错误状态处理

#### 5.5 专利管理页面数据集成 (10h)
- [ ] 任务列表加载
- [ ] 筛选与搜索
- [ ] 任务详情展示
- [ ] 进度实时更新
- [ ] 文档查看

#### 5.6 工作流监控页面数据集成 (12h)
- [ ] 实时事件流展示
- [ ] Agent 工作状态
- [ ] 阶段进度展示
- [ ] 日志查看
- [ ] 错误状态处理

#### 5.7 结果展示页面数据集成 (10h)
- [ ] 专利文档渲染
- [ ] 各阶段报告展示
- [ ] 下载功能
- [ ] 版本对比
- [ ] 重新生成

#### 5.8 Agent 管理页面数据集成 (12h)
- [ ] Agent 列表
- [ ] 配置编辑
- [ ] 工具管理
- [ ] 技能管理
- [ ] 记忆管理

#### 5.9 组织架构页面数据集成 (10h)
- [ ] 树形结构渲染
- [ ] 拖拽调整
- [ ] 节点编辑
- [ ] 权限控制

#### 5.10 SSE 实时事件集成 (8h)
- [ ] SSE 客户端封装
- [ ] 事件分发机制
- [ ] 断线重连
- [ ] 消息去重
- [ ] 状态同步

#### 5.11 用户认证与会话管理 (8h)
- [ ] 登录/注册页面
- [ ] Token 存储与刷新
- [ ] 会话过期处理
- [ ] 权限拦截
- [ ] 个人资料页面

#### 5.12 表单验证与错误处理 (6h)
- [ ] Zod 验证 schema
- [ ] 表单错误展示
- [ ] API 错误提示
- [ ] 错误边界

#### 5.13 加载状态与骨架屏优化 (6h)
- [ ] 页面加载骨架屏
- [ ] 列表加载状态
- [ ] 详情加载状态
- [ ] 按钮加载状态
- [ ] 优化用户体验

#### 5.14 响应式与移动端适配 (8h)
- [ ] 导航栏适配
- [ ] 聊天页面适配
- [ ] 表格响应式
- [ ] 触摸交互优化

---

## Phase 6: 第三方集成 (第 11-12 周)

**预计工时**: 122 小时
**目标**: 接入外部服务，增强系统能力

### 任务清单

#### 6.1 OpenAI API 集成 (8h)
- [ ] Chat Completions API
- [ ] Function Calling
- [ ] Embeddings API
- [ ] Token 消耗统计
- [ ] 错误处理与重试

**交付文件**:
- `backend/src/integrations/openai.py`

#### 6.2 Claude API 集成 (6h)
- [ ] Claude 3 API 集成
- [ ] 长上下文支持
- [ ] 统一接口封装

**交付文件**:
- `backend/src/integrations/anthropic.py`

#### 6.3 LLM Router (8h)
- [ ] 智能路由策略
- [ ] Fallback 机制
- [ ] 负载均衡
- [ ] 成本优化策略

**交付文件**:
- `backend/src/integrations/llm_router.py`

#### 6.4 Token 计数与成本管理 (6h)
- [ ] Token 精确计数
- [ ] 按模型定价
- [ ] 成本统计与报告
- [ ] 预算控制

**交付文件**:
- `backend/src/core/token_management.py`

#### 6.5 中国专利检索 API 集成 (16h)
- [ ] CNIPA 数据获取
- [ ] 专利详情查询
- [ ] 法律状态查询
- [ ] 数据解析与标准化
- [ ] 本地缓存策略

**交付文件**:
- `backend/src/integrations/cnipa.py`

#### 6.6 美国专利检索 API 集成 (12h)
- [ ] USPTO API 集成
- [ ] 数据解析
- [ ] 全文检索支持
- [ ] 缓存策略

**交付文件**:
- `backend/src/integrations/uspto.py`

#### 6.7 欧洲专利检索 API 集成 (12h)
- [ ] EPO OPS API 集成
- [ ] 数据解析
- [ ] 多语言支持

**交付文件**:
- `backend/src/integrations/epo.py`

#### 6.8 专利相似度算法实现 (16h)
- [ ] 文本向量化
- [ ] 相似度计算算法
- [ ] 批量对比优化
- [ ] 结果排序与过滤
- [ ] 性能基准测试

**交付文件**:
- `backend/src/analysis/similarity.py`

#### 6.9 Word 文档生成 (python-docx) (10h)
- [ ] 专利模板设计
- [ ] 权利要求书格式化
- [ ] 说明书格式化
- [ ] 格式合规检查
- [ ] 目录生成

**交付文件**:
- `backend/src/generators/docx_generator.py`

#### 6.10 PDF 文档生成 (ReportLab) (10h)
- [ ] PDF 模板设计
- [ ] 字体与样式
- [ ] 页眉页脚
- [ ] 页码与目录
- [ ] PDF/A 合规

**交付文件**:
- `backend/src/generators/pdf_generator.py`

#### 6.11 专利格式化与标准合规 (12h)
- [ ] 专利法格式要求
- [ ] 权利要求编号
- [ ] 术语一致性检查
- [ ] 格式自动化调整

**交付文件**:
- `backend/src/generators/patent_formatter.py`

#### 6.12 知识库向量搜索集成 (16h)
- [ ] pgvector 集成
- [ ] 向量索引构建
- [ ] 相似度搜索优化
- [ ] 混合搜索 (关键词 + 向量)
- [ ] 知识库增量更新

**交付文件**:
- `backend/src/knowledge/vector_store.py`

---

## Phase 7: 测试与优化 (第 13-15 周)

**预计工时**: 92 小时 (原 192h 缩减)
**目标**: 质量保证与性能优化

### 任务清单

#### 7.1 后端单元测试 (40h → 目标 80% 覆盖率)
- [ ] 核心基础设施测试
- [ ] 数据层测试
- [ ] Agent 逻辑测试
- [ ] API 接口测试
- [ ] 工具集成测试

#### 7.2 前端单元测试 (20h → 目标 70% 覆盖率)
- [ ] 组件测试
- [ ] Hook 测试
- [ ] Store 测试
- [ ] API 客户端测试

#### 7.3 API 集成测试 (8h)
- [ ] 端到端流程测试
- [ ] 权限测试
- [ ] 边界条件测试

#### 7.4 E2E 端到端测试 (Playwright) (12h)
- [ ] 核心用户流程测试
- [ ] 跨浏览器测试
- [ ] 回归测试

#### 7.5 性能测试与优化 (8h)
- [ ] 接口性能基准
- [ ] 数据库优化
- [ ] 缓存策略优化
- [ ] 慢查询优化

#### 7.6 安全测试与漏洞扫描 (4h)
- [ ] OWASP Top 10 检查
- [ ] 依赖漏洞扫描
- [ ] 权限绕过测试

#### 7.7 代码 Review 与重构 (0h)
- 持续在开发过程中进行

---

## 里程碑验收标准

### M1: 后端基础框架完成
- [ ] FastAPI 服务可运行
- [ ] 数据库可连接
- [ ] 基础 API 可调用
- [ ] 日志系统正常工作
- [ ] 代码通过 Lint 检查

### M2: Agent 核心完成
- [ ] 所有 5 个 Agent 可独立运行
- [ ] LLM 集成完成
- [ ] 工具系统可用
- [ ] 简单专利申请流程可跑通
- [ ] Agent 单元测试通过

### M3: API 服务完成
- [ ] 所有 API 端点实现
- [ ] SSE 事件流正常
- [ ] 认证系统工作
- [ ] API 文档自动生成
- [ ] 集成测试通过

### M4: 前端集成完成
- [ ] 所有页面接入真实 API
- [ ] 实时更新正常工作
- [ ] 错误处理完善
- [ ] 所有核心功能可用
- [ ] 响应式布局完成

### M5: 第三方集成完成
- [ ] 专利检索可用
- [ ] 文档生成正常
- [ ] 知识库搜索可用
- [ ] 成本统计准确

### M6: 测试与交付完成
- [ ] 测试覆盖率达标
- [ ] 性能指标达标
- [ ] 安全扫描通过
- [ ] 部署文档齐全
- [ ] 可部署到生产环境

---

## 关键依赖与风险

| 依赖项 | 影响范围 | 风险等级 | 缓解措施 |
|--------|---------|---------|---------|
| OpenAI API Key | 所有 Agent | 中 | 备用 Claude API |
| 专利检索 API | 检索分析 | 中 | 本地知识库兜底 |
| PostgreSQL + pgvector | 数据存储 | 高 | Docker 化部署 |
| Redis | 缓存/队列 | 中 | 内存兜底方案 |

---

**文档版本**: v1.0
**最后更新**: 2024-01-20
