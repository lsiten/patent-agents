# 专利智脑 - AI驱动的专利申请多智能体系统

![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue)
![React Version](https://img.shields.io/badge/React-18.2%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 项目概述

**专利智脑**是一个基于多智能体协作的自动化专利申请系统，采用**CEO Agent统筹 + 专业Agent分工**的分层架构，将专利申请全流程（需求分析→专利性检索→文件撰写→质量审查）完全自动化，大大提高专利申请效率和质量。

### 核心优势

| 特性 | 说明 |
|------|------|
| 🤖 **多智能体协作** | 5个专业Agent各司其职，CEO Agent全局协调 |
| 📚 **专业知识库** | 内置定稿专利知识库，写作风格参考与一致性保证 |
| 🔍 **多源检索** | 对接USPTO、EPO、CNIPA、Google Patents、arXiv等 |
| ✅ **智能审查** | 形式+实质双重审查，降低审查意见风险 |
| 🎨 **现代UI** | MongoDB Design System 设计语言，流畅用户体验 |
| 🔄 **实时监控** | SSE事件流推送，工作流进度可视化 |

---

## 系统架构

### 分层多智能体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户界面层 (Frontend)                     │
│   首页Hero  |  专利提交  |  流程监控  |  结果展示  |  下载中心   │
└─────────────────────────────────────────────────────────────────┘
                              ↕ SSE/REST
┌─────────────────────────────────────────────────────────────────┐
│                        CEO Agent (统筹层)                        │
│    流程调度  |  冲突协调  |  质量把控  |  迭代决策  |  交付集成  │
└─────────────────────────────────────────────────────────────────┘
                              ↕ 消息总线
┌─────────────────────────────────────────────────────────────────┐
│                      专业 Agent 层 (执行层)                       │
├────────────┬────────────┬──────────────┬────────────────────────┤
│ 需求分析   │ 检索分析   │ 专利撰写     │ 质量审查                 │
│ Agent      │ Agent      │ Agent        │ Agent                    │
│ 结构化需求 │ 专利性评估 │ 权利要求书   │ 形式合规检查             │
│ 创新点提取 │ 现有技术排查│ 说明书撰写   │ 实质内容审查             │
│ 类型推荐   │ 风险预警   │ 标准术语适配 │ 审查意见风险预估         │
└────────────┴────────────┴──────────────┴────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                       数据支撑层 (Data Layer)                     │
├──────────────────┬──────────────────┬───────────────────────────┤
│  定稿专利知识库  │  多源专利数据库  │    向量检索引擎 (可选)     │
│  • 风格参考      │  • USPTO         │    • FAISS / Milvus        │
│  • 写作范例      │  • EPO           │    • 相似专利匹配          │
│  • 质量评分      │  • CNIPA         │    • 现有技术比对          │
│                  │  • Google Patents│                           │
│                  │  • arXiv          │                           │
└──────────────────┴──────────────────┴───────────────────────────┘
```

---

## 快速开始

### 环境要求

- **后端**: Python 3.11+
- **前端**: Node.js 18+
- **浏览器**: Chrome 90+ / Firefox 88+ / Safari 14+

### 一键启动 (推荐)

#### macOS/Linux

```bash
# 1. 克隆项目
git clone <repository-url>
cd patent-agents

# 2. 启动后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置你的 API Key
python main.py

# 3. 启动前端 (新终端)
cd ../frontend
npm install
npm run dev
```

#### Windows

```powershell
# 后端 
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python main.py

# 前端 (新终端)
cd frontend
npm install
npm run dev
```

### 访问服务

- 前端界面: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

---

## 项目结构

```
patent-agents/
├── backend/                          # 🐍 后端服务
│   ├── src/
│   │   ├── agents/                   # 🤖 Agent 实现
│   │   │   ├── base.py               # Agent 基类
│   │   │   ├── ceo.py                # CEO 统筹 Agent
│   │   │   ├── requirement_analyst.py # 需求分析 Agent
│   │   │   ├── retrieval_analyst.py  # 检索分析 Agent
│   │   │   ├── patent_writer.py      # 专利撰写 Agent
│   │   │   └── quality_reviewer.py   # 质量审查 Agent
│   │   ├── core/                     # 🔧 核心组件
│   │   │   └── workflow.py           # 状态机与工作流引擎
│   │   ├── models/                   # 📊 数据模型
│   │   │   ├── domain.py             # 领域模型
│   │   │   ├── enums.py              # 枚举定义
│   │   │   └── __init__.py
│   │   ├── api/                      # 🌐 API 层
│   │   │   ├── routes.py             # API 路由
│   │   │   └── schemas.py            # 请求/响应 Schema
│   │   ├── knowledge/                # 📚 知识库
│   │   │   └── base.py               # 本地文件知识库
│   │   ├── data_sources/             # 🔍 数据源集成
│   │   │   └── base.py               # 多源检索管理器
│   │   ├── prompts/                  # 💬 Prompt 模板
│   │   │   └── templates.py          # 各 Agent 提示词
│   │   ├── tools/                    # 🛠️ 工具函数
│   │   └── utils/                    # 🔧 工具类
│   ├── finalized_patents/            # 📦 定稿专利存储
│   ├── exports/                      # 📤 导出文件目录
│   ├── tests/                        # ✅ 测试用例
│   ├── main.py                       # 🚀 应用入口
│   ├── requirements.txt              # 📋 Python 依赖
│   └── pyproject.toml                # 🎯 项目配置
│
├── frontend/                         # ⚛️ 前端应用
│   ├── app/                          # Next.js App Router
│   │   ├── layout.tsx                # 根布局
│   │   ├── page.tsx                  # 首页
│   │   ├── globals.css               # 全局样式
│   │   ├── submit/                   # 专利提交页面
│   │   ├── workflow/[taskId]/        # 流程监控页面
│   │   └── result/[taskId]/          # 结果展示页面
│   ├── components/
│   │   ├── layout/                   # 布局组件
│   │   │   ├── Navbar.tsx
│   │   │   ├── Hero.tsx
│   │   │   └── Footer.tsx
│   │   ├── workflow/                 # 工作流组件
│   │   │   ├── ProgressStepper.tsx
│   │   │   ├── AgentCard.tsx
│   │   │   └── MessageLog.tsx
│   │   └── ui/                       # 基础 UI 组件
│   │       ├── Button.tsx
│   │       ├── Card.tsx
│   │       ├── Badge.tsx
│   │       ├── Input.tsx
│   │       ├── Tabs.tsx
│   │       └── CodeBlock.tsx
│   ├── types/                        # 📘 TypeScript 类型
│   └── package.json
│
├── DESIGN.md                         # 🎨 设计系统规范 (MongoDB风格)
├── README.md                         # 📖 本文件
└── .gitignore
```

---

## Agent 详细说明

### CEO Agent (统筹者)

**核心职责**:
- 全局流程调度和状态机管理
- 跨Agent信息传递和冲突协调
- 质量把控和迭代优化决策
- 异常处理和风险预警

**关键能力**:
- 工作流状态机控制
- 任务分发和结果汇总
- 质量门限检查
- 用户通知触发

---

### 需求分析 Agent (解构者)

**核心职责**:
- 深度理解非结构化技术描述
- 提取关键创新点和区别技术特征
- 判定适合的专利类型（发明/实用新型/外观设计）
- 识别信息缺口并提示补充

**输出结构**:
```json
{
  "tech_field": "人工智能 / 自然语言处理",
  "core_principle": "基于Transformer架构的多模态理解",
  "application_scenarios": ["智能客服", "医疗咨询"],
  "key_features": [
    {"name": "多模态融合", "is_innovative": true}
  ],
  "patent_type": "invention",
  "confidence": 0.92
}
```

---

### 检索分析 Agent (评估者)

**核心职责**:
- 多源并行检索现有技术
- 新颖性、创造性、实用性评估
- 高风险对比文件识别
- 撰写策略建议

**支持的数据源**:
| 数据源 | 状态 | 说明 |
|--------|------|------|
| USPTO | ✅ | 美国专利商标局开放API |
| EPO | ✅ | 欧洲专利局OPS服务 |
| Google Patents | ✅ | 浏览器自动化检索 |
| arXiv | ✅ | 学术论文检索 |
| CNIPA | 🚧 | 中国国家知识产权局 |

---

### 专利撰写 Agent (创作者)

**核心职责**:
- 独立权利要求 + 从属权利要求撰写
- 说明书五大部分完整撰写
- 标准专利术语规范使用
- 参考知识库中的优秀范例风格

**输出文件结构**:
```
专利申请文件
├── 权利要求书
│   ├── 独立权利要求1
│   └── 从属权利要求2-N
├── 说明书
│   ├── 技术领域
│   ├── 背景技术
│   ├── 发明内容
│   ├── 附图说明
│   └── 具体实施方式
├── 说明书摘要
└── 关键术语表
```

---

### 质量审查 Agent (把关者)

**核心职责**:
- **形式合规性**: 格式、编号、术语、引用关系检查
- **权利要求审查**: 清楚性、简要性、支持性检查
- **说明书审查**: 公开充分性、支持性检查
- **一致性审查**: 权利要求与说明书对应关系检查
- **审查风险预估**: 预测审查员可能提出的审查意见

---

## API 接口文档

### 核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/tasks` | 创建专利申请任务 |
| `GET` | `/api/v1/tasks` | 获取任务列表 |
| `GET` | `/api/v1/tasks/{taskId}` | 获取任务详情 |
| `GET` | `/api/v1/tasks/{taskId}/stream` | SSE实时事件流 |
| `GET` | `/api/v1/tasks/{taskId}/events` | 获取任务事件 |
| `POST` | `/api/v1/tasks/{taskId}/cancel` | 取消任务 |
| `POST` | `/api/v1/search/patents` | 专利检索 |
| `GET` | `/api/v1/knowledge/search` | 知识库搜索 |
| `GET` | `/api/v1/system/status` | 系统状态 |

### 示例: 创建任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tech_description": "本发明涉及一种基于多模态的智能对话系统...",
    "patent_type_preference": "invention",
    "user_id": "user_001"
  }'
```

### 示例: SSE事件流监听

```javascript
const eventSource = new EventSource(
  `http://localhost:8000/api/v1/tasks/${taskId}/stream`
);

eventSource.addEventListener('info', (e) => {
  console.log('信息:', JSON.parse(e.data));
});

eventSource.addEventListener('success', (e) => {
  console.log('完成:', JSON.parse(e.data));
});

eventSource.addEventListener('done', (e) => {
  console.log('工作流结束:', e.data);
  eventSource.close();
});
```

---

## 设计系统

本项目严格遵循 **MongoDB Design System** 设计语言，详细规范请参考 [`DESIGN.md`](./DESIGN.md)。

### 视觉特色

- **主色调**: MongoDB 绿 (`#00ed64`) - 活力、创新、可信
- **深色Hero**: 深海军蓝 (`#001e2b`) - 专业、技术感
- **圆角体系**: 按钮全圆角、卡片12px、输入框8px
- **排版层级**: Hero大标题、清晰的信息层级、充足留白

### 组件库

| 组件 | 状态 |
|------|------|
| Button | ✅ 5种变体 |
| Card | ✅ 特色卡片、定价卡片等 |
| Badge | ✅ 绿色/紫色/橙色/灰色 |
| Input | ✅ 文本输入、文本域 |
| Tabs | ✅ 分段式、胶囊式 |
| CodeBlock | ✅ 代码展示、终端风格 |
| Stepper | ✅ 进度步进器 |
| MessageLog | ✅ 实时日志流 |

---

## 配置说明

### 后端配置 (`backend/.env`)

```bash
# LLM配置
OPENAI_API_KEY=sk-xxx
LLM_MODEL=gpt-4-turbo-preview

# 数据源配置
USPTO_API_KEY=xxx
EPO_CONSUMER_KEY=xxx
EPO_CONSUMER_SECRET=xxx

# 工作流配置
MAX_ITERATIONS=3
```

### 浏览器自动化 (可选)

如需使用 Google Patents 浏览器检索功能：

```bash
cd backend
source venv/bin/activate
pip install playwright
playwright install chromium
```

---

## 开发指南

### 后端开发

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env
python main.py
```

代码质量检查:
```bash
black src/
isort src/
flake8 src/
mypy src/
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
```

类型检查:
```bash
npx tsc --noEmit
```

---

## 测试

### 后端测试

```bash
cd backend
pytest tests/ -v --cov=src
```

### 端到端测试

```bash
# 启动后端服务
cd backend && python main.py

# 启动前端服务
cd frontend && npm run dev

# 访问 http://localhost:3000 进行手动测试
```

---

## 部署

### Docker 部署 (推荐)

```bash
# 后端
cd backend
docker build -t patent-agents-backend .
docker run -p 8000:8000 -e OPENAI_API_KEY=xxx patent-agents-backend

# 前端
cd frontend
docker build -t patent-agents-frontend .
docker run -p 3000:3000 patent-agents-frontend
```

### Vercel 部署 (前端)

```bash
cd frontend
vercel --prod
```

### 生产环境配置建议

1. 使用 PostgreSQL 替换 SQLite
2. 启用 Redis 任务队列
3. 接入向量数据库 (Milvus/FAISS)
4. 配置 Nginx 反向代理和HTTPS
5. 启用 API 认证和限流
6. 配置日志收集和监控告警

---

## 路线图

| 版本 | 功能 | 状态 |
|------|------|------|
| v1.0 | 核心多智能体框架 + 前端界面 | ✅ 完成 |
| v1.1 | 接入真实 LLM API + 向量检索 | 🚧 进行中 |
| v1.2 | CNIPA中文专利数据库对接 | 📅 计划 |
| v1.3 | PDF/DOCX 专业格式导出 | 📅 计划 |
| v1.4 | 电子申请系统对接 | 📅 计划 |
| v2.0 | Agent 自学习与知识库进化 | 📅 规划 |

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 技术支持

如有问题或建议，请:
1. 查看 [Issues](../../issues)
2. 提交新的 [Issue](../../issues/new)

---

**Made with ❤️ for Innovators**

> 让创新更有价值
