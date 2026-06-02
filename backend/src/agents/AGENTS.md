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

### Per-Agent LLM / ImageGen Configuration

每个 agent 可独立配置 LLM 供应商（provider / base_url / api_key / model）和生图供应商，**缺失字段时回退全局默认**。配置分三层，按优先级合并：

| 优先级 | 来源 | 位置 | 用途 |
|-------|------|------|------|
| 1 (最高) | runtime override | `backend/src/data/agent_overrides.json` → `llm_override` / `image_gen_override` | 前端 UI 改的；api_key 用 Fernet 加密 |
| 2 | agent yaml | `hermes_home/profiles/<agent>/config.yaml` → `llm` / `image_gen` | 开发者 / CI 配的；支持 `${ENV_VAR}` 引用 |
| 3 | system-config 默认 | `hermes_home/profiles/system-config/config.yaml` → `llm` / `image_gen` | 跨 agent 的兜底 |
| 4 (最低) | 全局 settings | `src/core/config.py` → `LLMSettings` / `ImageGenSettings` 的 `active_provider` | 最终兜底 |

#### YAML 配置示例（`hermes_home/profiles/patent_writer/config.yaml`）
```yaml
llm:
  provider: openai
  base_url: ${WRITER_LLM_BASE_URL}     # 引用环境变量
  api_key: ${WRITER_OPENAI_API_KEY}    # 引用环境变量（不会被 git 泄露）
  model: gpt-4o

image_gen:
  provider: openai
  model_id: dall-e-3
```

#### runtime override 示例（`agent_overrides.json`）
```json
{
  "patent.writer.v1": {
    "llm_override": {
      "provider": "openai",
      "base_url": "https://my-proxy.example/v1",
      "api_key": "enc:gAAAAABq...",   # Fernet 加密
      "model": "gpt-4o"
    }
  }
}
```

#### API 端点
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/agents/{id}` | 返回 `llm_config` 和 `image_gen_config`（含 `source` / `is_default` 溯源 + masked key） |
| PUT | `/api/agents/{id}/llm-config` | 更新 LLM override（`use_default: true` 清除） |
| PUT | `/api/agents/{id}/image-gen-config` | 更新生图 override |
| POST | `/api/agents/{id}/llm-config/test` | 测试连通性（5s 超时） |
| POST | `/api/agents/{id}/image-gen-config/test` | 测试生图连通性 |

#### 安全
- API key 落盘前用 Fernet 加密，主密钥来源：
  1. 环境变量 `AGENT_OVERRIDE_MASTER_KEY`（推荐）
  2. `<DATA_DIR>/.secret_key`（自动生成，权限 0600）
- 主密钥一旦丢失，加密的 API key 全部不可恢复（设计如此）
- 前端展示用 `sk-***xxxx` 格式脱敏

#### 单元 / 集成测试
- `tests/test_secret_cipher.py` — Fernet 加解密（10 个测试）
- `tests/test_config_resolve.py` — `resolve_for_agent` 优先级（17 个测试）
- `tests/test_agent_config_resolution.py` — `${ENV_VAR}` 展开 + yaml fallback（12 个测试）
- `tests/test_override_store_llm.py` — 加密覆盖存储（13 个测试）
- `tests/test_per_agent_config_integration.py` — 端到端优先级链（9 个测试）
