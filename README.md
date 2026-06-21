# 专利智脑

专利智脑是一个面向“未申请专利”的多 Agent 专利撰写系统。系统从交底文件或发明沟通内容中梳理专利主题，经过头脑风暴、专利名确认、需求分析、检索补证、分段撰写、质量审查和 DOCX 生成，输出可用于申请准备的专利申请文件。

## 当前架构

```text
用户
  ↕
Next.js 前端（REST + SSE + AG-UI 事件归并）
  ↕
FastAPI 后端
  ↕
LangGraph StateGraph 工作流运行时
  ↕
Hermes Agent 团队（run_agent.AIAgent）
  ↕
Hermes Tools / 检索源 / 附图生成 / DOCX 生成
```

核心原则：

- Hermes `run_agent.AIAgent` 是专业 Agent 执行底座。
- LangGraph 负责工作流图、状态、checkpoint、interrupt 和条件路由。
- AG-UI 事件协议负责前后端实时状态同步、工具过程、阶段轮次和刷新恢复。
- CEO Agent 只做调度和共享事实维护，不替专业 Agent 下专业结论。
- 需求分析、检索、撰写、质量审查每个阶段都有输入/输出契约和质量门。
- 不允许 mock 内容、案例专用规则或内容兜底；确定性规则本地检查，专业判断交给对应 Agent。

## 工作流

```text
brainstorm
  → title_generation
  → human_confirm_start
  → requirement_analysis
  → requirement_gate
  → retrieval
  → retrieval_gate
  → writing
  → writing_gate
  → quality_review
  → quality_gate
  → final_docx
```

如果质量审查低于阈值或存在关键问题，LangGraph 条件边会把问题路由回对应专业 Agent。每轮修改必须基于上一轮内容和反馈继续优化；通过质量门后，确认事实写入全局 `shared_facts`，所有 Agent 共用同一份公共事实。

## 目录结构

```text
backend/
  main.py                         FastAPI 入口
  hermes_home/profiles/           Hermes Agent profile、SOUL、skills
  src/
    api/                          REST/SSE 路由，按 conversations/workflows/agents/system 分域
    agents/                       Hermes Agent 配置加载、tool adapter、运行桥接
    core/
      constants/                  运行环境、专利硬规则、工作流超时等常量
      llm/
        client.py                 统一 LLM client/service
        providers/                内置文字 LLM 与生图 provider catalog
      workflow/                   LangGraph runtime、nodes、contracts、gates、events、artifact writer
      patent/                     专利规范确定性检查
      config.py                   pydantic-settings 配置入口
    data_sources/                 专利库、论文、网页和权威来源连接器
    document_gen/                 DOCX/附图/模板生成
    models/                       SQLAlchemy/Pydantic 模型
    repositories/                 数据访问层
    services/                     业务服务层

frontend/
  app/                            Next.js App Router 页面
  components/
    chat/                         对话页、输入框、工作流状态条
    workflow/                     工作流详情、阶段输出、多轮 tab、日志
    ui/                           基础 UI
  lib/
    api/                          REST/SSE client
    constants/                    前端运行时常量
    workflowProtocolStore.ts      AG-UI 事件归并和刷新恢复
```

## 常量与内置 Provider

后端常量集中在 `backend/src/core/constants/`：

- `environment.py`：环境名、默认环境、环境变量文件映射。
- `patent_rules.py`：权利要求步数、字数、必备章节、交底稿噪声标记。
- `workflow.py`：质量循环阈值、循环上限、Agent/撰写超时。

内置 LLM 和生图 provider 集中在 `backend/src/core/llm/providers/catalog.py`：

- 文字 LLM：`openai`、`anthropic`、`deepseek`、`openrouter`、`spark`、`openai-spark`。
- 生图：`azure_aoai`、`openai`、`stability`。
- 目录只保存 provider 元数据、默认 base URL、默认模型和环境变量名，不保存 API key。

前端运行时常量集中在 `frontend/lib/constants/runtime.ts`：

- API base URL。
- SSE 重连策略。
- 对话列表与工作流同步轮询间隔。
- 聊天流超时与退避策略。

## 配置

使用 `./start.sh` 时，三套环境可以同时运行：

| 模式 | 前端 | 后端 | 环境文件 |
| --- | --- | --- | --- |
| `dev` | `3000` | `8000` | `backend/.env` |
| `test` | `3100` | `8100` | `backend/.env.testing` |
| `production` | `10001` | `10002` | `backend/.env.production` |

示例：

```bash
./start.sh dev
./start.sh test
./start.sh production
```

LLM 与生图配置优先级：

1. Agent runtime override：`backend/var/agent_overrides.json`
2. Agent profile YAML：`backend/hermes_home/profiles/<agent>/config.yaml`
3. System config profile：`backend/hermes_home/profiles/system-config/config.yaml`
4. 全局 settings：`backend/src/core/config.py`

系统配置保存后会重新加载 settings，并重置 LLM client/service 缓存。

## 专利生成要求

生成结果必须符合：

- `专利申请文件撰写完整规范手册.md`
- 当前补充硬规则：权利要求 1 的独权部分只能由 3 步或 4 步组成。
- 当前补充硬规则：权利要求书中每个分号和句号后必须换行。
- 附图必须由真实专利内容决定，编号、标题、正文引用和 DOCX 插入位置一致。
- 检索源未配置时禁用，不可用时记录并跳过；专利库无结果时依次查论文、公开网页和权威网站。
- 信息不足时先由对应 Agent 尝试补证；仍无法可靠解决时，明确向用户请求补充。

## 开发与验证

常用命令：

```bash
# 后端测试
cd backend
PYTHONPATH=. python -m pytest

# 前端类型检查
cd frontend
npm run typecheck

# 启动脚本隔离测试
bash scripts/test_start_sh_isolation.sh
```

浏览器验收必须真实操作页面：

1. 打开 `http://localhost:3000/chat`。
2. 上传交底文件或输入技术内容。
3. 等待头脑风暴与专利名生成。
4. 用户确认后启动正式流程。
5. 等待需求分析、检索、分段撰写、附图、质量审查和 DOCX 生成。
6. 下载 DOCX，并校验章节、权利要求、换行、附图一致性和规范硬规则。

## 文档

- `docs/langgraph-hermes-agui-workflow-optimization.md`：LangGraph + Hermes + AG-UI 工作流设计。
- `docs/runtime-constants-and-provider-catalog.md`：运行时常量与内置 LLM/生图 provider 目录。
- `docs/langgraph-hermes-agui-compliance-audit.md`：架构符合度审计。
- `docs/agent-activity-logging-architecture.md`：Agent 工具/技能/日志展示方案。
- `docs/api-spec.md`：API 说明。
- `docs/database-schema.md`：数据模型说明。
