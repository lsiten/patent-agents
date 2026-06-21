# 运行时常量与内置 Provider 目录

## 目标

项目不再把通用常量、运行时策略、专利硬规则和内置 LLM/生图 provider 分散写在 API、workflow、config 或 UI 组件中。所有新增配置项应先判断属于哪一类，再放到对应目录。

## 后端常量

### `backend/src/core/constants/environment.py`

用途：运行环境与环境文件映射。

当前包含：

- `ENV_DEVELOPMENT`
- `ENV_TESTING`
- `ENV_STAGING`
- `ENV_PRODUCTION`
- `DEFAULT_ENVIRONMENT`
- `ENV_FILE_BY_ENVIRONMENT`

维护规则：

- `start.sh`、`config.py`、测试隔离脚本使用相同环境命名。
- 新增环境时同步扩展环境文件映射，避免散落条件判断。

### `backend/src/core/constants/patent_rules.py`

用途：确定性专利硬规则。

当前包含：

- `INDEPENDENT_CLAIM_ALLOWED_STEP_COUNTS`
- `INDEPENDENT_CLAIM_MAX_CHARS`
- `DEPENDENT_CLAIM_MAX_CHARS`
- `PATENT_REQUIRED_SECTIONS`
- `TRANSCRIPT_ARTIFACT_MARKERS`

维护规则：

- 只放确定、可代码化检查的硬规则。
- 不放某个案例、某个技术领域或某份交底文件的关键词。
- 内容质量、创造性、充分公开等专业判断应由对应 Hermes Agent 通过 LLM 完成。

### `backend/src/core/constants/workflow.py`

用途：工作流循环阈值和超时策略。

当前包含：

- `QUALITY_REMEDIATION_THRESHOLD`
- `QUALITY_REMEDIATION_SAFETY_LIMIT`
- `WRITER_INITIAL_TIMEOUT_SECONDS`
- `WRITER_REVISION_TIMEOUT_SECONDS`
- `WRITER_DRAWING_REPAIR_TIMEOUT_SECONDS`
- `AGENT_CONVERSATION_TIMEOUT_SECONDS`

维护规则：

- 阶段超时、质量循环上限、评分阈值统一放这里。
- 不要在 `core/workflow/` 节点文件里直接写魔法数字。

## 前端常量

### `frontend/lib/constants/runtime.ts`

用途：前端运行时连接、SSE 重连、轮询和聊天流策略。

当前包含：

- `DEFAULT_API_BASE_URL`
- `API_BASE_URL`
- `SSE_RECONNECT`
- `POLLING_INTERVALS`
- `CHAT_STREAM_DEFAULTS`

维护规则：

- 组件中不要直接写 `localhost:8000`、SSE 最大重试次数或工作流轮询间隔。
- UI 动效短延迟可以留在局部组件；跨页面运行时策略必须进该文件。

## 内置文字 LLM Provider

目录：`backend/src/core/llm/providers/catalog.py`

当前文字 provider：

| Provider | Category | Default Base URL | Default Model | Client |
| --- | --- | --- | --- | --- |
| `openai` | text | `https://api.openai.com/v1` | `gpt-4-turbo-preview` | OpenAI-compatible |
| `anthropic` | text | `https://api.anthropic.com/v1` | `claude-3-opus-20240229` | Anthropic |
| `deepseek` | text | `https://api.deepseek.com/v1` | `deepseek-chat` | OpenAI-compatible |
| `openrouter` | text | `https://openrouter.ai/api/v1` | `openrouter/auto` | OpenAI-compatible |
| `spark` | text | `https://spark-api-open.xf-yun.com/v1` | `generalv3.5` | OpenAI-compatible |
| `openai-spark` | text | `https://spark-api-open.xf-yun.com/v1` | `generalv3.5` | OpenAI-compatible |

每个 provider 声明：

- provider id
- 展示名称
- 分类
- base URL 环境变量名
- model 环境变量名
- API key/secret 环境变量名
- 默认 base URL
- 默认模型
- 是否 OpenAI-compatible

## 内置生图 Provider

目录：`backend/src/core/llm/providers/catalog.py`

当前生图 provider：

| Provider | Category | Default Base URL | Default Model |
| --- | --- | --- | --- |
| `azure_aoai` | image | `http://deepseek-work.intsig.net/proxy/azure/gpt/v1` | `gpt-image-2` |
| `openai` | image | `https://api.openai.com/v1` | `dall-e-3` |
| `stability` | image | `https://api.stability.ai/v1` | `stable-diffusion-3` |

## 安全规则

- Provider catalog 不能包含真实 API key。
- Agent profile YAML 可以引用环境变量，例如 `${WRITER_OPENAI_API_KEY}`。
- Runtime override 中的 API key 必须加密落盘。
- 系统配置保存后必须重新加载 settings 并重置 LLM service 缓存。

## 新增常量或 Provider 的流程

1. 判断配置属于后端环境、专利硬规则、工作流策略、前端运行时，还是 LLM provider。
2. 放入对应 constants/provider 文件。
3. 替换原调用点中的硬编码。
4. 更新 README 或本文件。
5. 增加或调整测试，避免重复硬编码回流。
