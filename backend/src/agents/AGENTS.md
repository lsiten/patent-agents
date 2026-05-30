## agents/ — Multi-Agent System

### Architecture (hermes-agent based)
```
agent_config.py         ← 配置加载模块，从 hermes_home/profiles/ 读取 YAML
  ↓
create_ai_agent()       ← 创建 AIAgent 实例 (hermes-agent 包)
  ↓
hermes/tools/           ← 21 个专利工具实现 + adapter 桥接
```

### Agent Roles (6 profiles in `hermes_home/profiles/`)
| Agent | Profile ID | Role |
|-------|------------|------|
| CEO | patent.ceo.v1 | Workflow orchestrator, delegates tasks |
| Requirement Analyst | patent.requirement_analyst.v1 | Extracts patent requirements from invention descriptions |
| Retrieval Analyst | patent.retrieval_analyst.v1 | Searches prior art, patent databases |
| Patent Writer | patent.writer.v1 | Drafts patent specifications, claims |
| Quality Reviewer | patent.quality_reviewer.v1 | Reviews drafts for completeness, compliance |
| Brainstorm Partner | patent.brainstorm_partner.v1 | Creative exploration of embodiments |

### Configuration Structure
```
hermes_home/
├── profiles/
│   ├── ceo/
│   │   ├── config.yaml    ← Agent 配置 (model, tools, temperature...)
│   │   └── SOUL.md        ← System prompt
│   ├── patent_writer/
│   ├── requirement_analyst/
│   ├── retrieval_analyst/
│   ├── quality_reviewer/
│   └── brainstorm_partner/
├── sessions/              ← 会话持久化
└── SOUL.md                ← 全局 system prompt
```

### Key Exports (`__init__.py`)
- `AgentConfig` / `AgentConfigRegistry` — 配置加载
- `get_agent_config()` / `get_agent_config_registry()` — 配置访问
- `create_ai_agent()` — 创建 AIAgent 实例

### Usage Pattern
```python
from src.agents import create_ai_agent

# 创建 Agent
agent = create_ai_agent(
    profile_id="patent.ceo.v1",
    session_id="ses_xxx",
    callbacks={
        "tool_start": lambda call_id, name, args: ...,
        "tool_complete": lambda call_id, name, args, result: ...,
        "thinking": lambda text: ...,
        "stream_delta": lambda delta: ...,
    }
)

# 运行对话
result = await agent.run_conversation("分析这个技术方案...")
# result = {"final_response": str, "messages": list, "completed": bool, ...}
```
