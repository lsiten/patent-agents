# 项目总结 - 专利智脑

## 当前定位

专利智脑是一个基于 Hermes Agent、LangGraph 和 AG-UI 的专利申请文件生成系统。它面向尚未申请、尚未公开的技术方案，通过多 Agent 协作把交底沟通内容整理为可用于申请准备的专利 DOCX。

## 已完成的主链路能力

| 能力 | 当前状态 |
| --- | --- |
| Hermes Agent 底座 | 使用 `run_agent.AIAgent`，profile 位于 `backend/hermes_home/profiles/` |
| LangGraph 工作流 | 使用 `StateGraph` 表达阶段、质量门、用户 interrupt 和失败路由 |
| AG-UI 事件 | 后端统一输出工作流/工具/技能/阶段轮次事件，前端归并恢复 |
| 头脑风暴 | 正式流程启动前先梳理专利方向和技术细节 |
| 专利名生成 | 启动确认前必须生成并展示专利名称 |
| 用户确认 | 不能仅凭提示词或上传文件自动启动正式申请流程 |
| 需求分析 | 识别技术需求、创新点、缺口和待解决问题 |
| 检索补证 | 按缺口检索专利库、论文、公开网页和权威来源 |
| 分段撰写 | 撰写 Agent 分段生成专利内容，并逐步写入 DOCX 结构 |
| 附图生成 | 撰写 Agent 根据真实专利内容生成附图并插入文档 |
| 质量审查 | 低于 90 分或存在 critical/high 问题时路由回责任 Agent |
| 多轮展示 | 每阶段每轮输出写入 `phase_rounds`，前端以 tab 展示 |
| 共享事实 | 通过 `shared_facts` 在所有 Agent 间共享已确认信息 |
| 配置隔离 | dev/test/production 可同时启动，端口和 Next dist 目录互不覆盖 |

## 最新工程结构

```text
backend/src/
  api/                         API 路由与 SSE
  agents/                      Hermes Agent 配置、adapter、tools
  core/
    constants/                 抽离后的全局常量
    llm/providers/             内置文字 LLM 与生图 provider catalog
    workflow/                  LangGraph runtime、节点、契约、质量门、事件、产物
    patent/                    专利硬规则检查
    config.py                  settings 与 runtime reload
  data_sources/                外部数据源连接
  document_gen/                DOCX 与附图生成
  models/                      数据模型
  repositories/                持久化访问
  services/                    业务服务

frontend/
  app/                         Next.js 页面
  components/chat/             对话主界面、输入框、流程状态条
  components/workflow/         工作流详情、阶段输出、多轮展示、日志
  lib/constants/               前端运行时常量
  lib/workflowProtocolStore.ts AG-UI 事件归并
```

## 常量抽离结果

| 分类 | 文件 |
| --- | --- |
| 环境常量 | `backend/src/core/constants/environment.py` |
| 专利规范硬规则 | `backend/src/core/constants/patent_rules.py` |
| 工作流阈值与超时 | `backend/src/core/constants/workflow.py` |
| 前端运行时常量 | `frontend/lib/constants/runtime.ts` |

## 内置 LLM / 生图配置

内置 provider 元数据集中在 `backend/src/core/llm/providers/catalog.py`。

文字 LLM：

- `openai`
- `anthropic`
- `deepseek`
- `openrouter`
- `spark`
- `openai-spark`

生图：

- `azure_aoai`
- `openai`
- `stability`

该目录只保存 provider 分类、默认 base URL、默认模型和环境变量名。API key 必须通过环境变量、系统配置或 Agent override 注入，不写入代码。

## 启动方式

```bash
./start.sh dev         # frontend 3000, backend 8000
./start.sh test        # frontend 3100, backend 8100
./start.sh production  # frontend 10001, backend 10002
```

三种模式可以同时运行。

## 质量要求

- 生成 DOCX 必须符合 `专利申请文件撰写完整规范手册.md`。
- 权利要求 1 的独权部分只能由 3 或 4 步组成。
- 权利要求书每个分号和句号后必须换行。
- 不能保留逐字稿格式内容、时间戳或交底文件格式噪声。
- 附图编号、标题、正文引用和文档插入必须一致。
- 检索结果不足时必须分析原因并更换检索策略；仍不足时再请求用户补充。
- 所有专业判断由对应 Agent 通过 LLM 完成，确定性硬规则才允许本地检查。

## 验证入口

```bash
cd backend && PYTHONPATH=. python -m pytest
cd frontend && npm run typecheck
bash scripts/test_start_sh_isolation.sh
```

最终验收仍以真实浏览器生成一份专利、下载 DOCX 并校验规范为准。
