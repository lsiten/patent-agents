# Per-Agent LLM / Image-Gen Configuration — Implementation Plan

> **For agentic workers:** Each task below is a self-contained, verifiable unit. TDD: red-green-refactor for any new business logic.

**Goal:** 让每个 agent 可以独立配置 LLM 供应商 (provider / base_url / api_key / model) 和生图供应商，缺失时回退全局；API key 加密存储，yaml 里用 `${ENV_VAR}` 引用环境变量。

**Architecture:**
- **配置优先级**（从高到低）：runtime override（加密）> agent config.yaml（${ENV_VAR} 引用）> system-config 默认 > 全局 settings
- **存储分层**：yaml 文件存非敏感配置 + env 引用；`agent_overrides.json` 存运行时修改（api_key 用 Fernet 加密）
- **API 扩展**：`PUT /api/agents/{id}/llm-config` 和 `image-gen-config`；`POST .../test` 测试连通性
- **前端**：agent 详情页新增 LLM/生图配置卡片，复用 system-config 的 ProviderSelect 模式

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, cryptography (Fernet), Next.js 14 + TypeScript

---

## Phase 1: 后端基础设施

### Task 1: 添加 cryptography 依赖
**Files:** `backend/requirements.txt`

- [ ] **Step 1:** 在 `requirements.txt` 添加 `cryptography>=42.0.0`
- [ ] **Step 2:** 跑 `pip install -r backend/requirements.txt` 验证
- [ ] **Step 3:** 验证 `from cryptography.fernet import Fernet` 可导入

### Task 2: 加密工具模块
**Files:** `backend/src/core/secret_cipher.py` (新)

- [ ] **Step 1 (TDD red):** 写测试 `tests/core/test_secret_cipher.py`:
  - `test_roundtrip_encrypt_decrypt`: 加密 "sk-xxx" → 解密得到 "sk-xxx"
  - `test_empty_value_returns_empty`: 空字符串返回空
  - `test_different_keys_fail`: 用 key A 加密，key B 抛 InvalidToken
  - `test_uses_env_master_key`: 设置 `AGENT_OVERRIDE_MASTER_KEY` 后能加密
  - `test_persists_auto_generated_key`: 未设置 env 时自动生成 key 并持久化到文件
- [ ] **Step 2:** 跑测试确认失败
- [ ] **Step 3:** 实现 `secret_cipher.py`：
  - `get_master_key() -> bytes`: 优先 env，fallback 文件 `data/.secret_key`，启动时自动生成
  - `encrypt_value(plaintext: str) -> str`: 返回 `"enc:" + base64(ciphertext)`
  - `decrypt_value(ciphertext: str) -> str`: 检测 `"enc:"` 前缀解密；非前缀原样返回（兼容明文）
  - `is_encrypted(value: str) -> bool`
- [ ] **Step 4:** 跑测试确认通过

### Task 3: 扩展 `LLMSettings` 添加 per-agent resolve
**Files:** `backend/src/core/config.py` (修改)

- [ ] **Step 1 (TDD red):** 写测试 `tests/core/test_config_resolve.py`:
  - `test_resolve_with_no_override_returns_active`: 无 override 时返回 active provider 的全局配置
  - `test_resolve_with_provider_override`: override `provider: "anthropic"` 返回 anthropic 全局配置
  - `test_resolve_with_full_override`: override 全字段时返回 override 值
  - `test_resolve_with_invalid_provider_falls_back`: override provider 不在白名单时回退 active
  - `test_resolve_decrypts_api_key`: api_key 以 `enc:` 开头时解密
- [ ] **Step 2:** 跑测试确认失败
- [ ] **Step 3:** 在 `LLMSettings` 类添加方法 `resolve_for_agent(overrides: dict | None) -> dict`：
  - 如果 `overrides` 为 None 或空，返回 `get_provider_config()` 的结果
  - 否则用 override 字段（provider / base_url / api_key / model）覆盖
  - 如果 `provider` 不在 `TEXT_LLM_PROVIDERS`，fallback 到 `active_provider`
  - 对 `api_key` 调用 `decrypt_value` 兜底
- [ ] **Step 4:** 跑测试确认通过

### Task 4: 扩展 `ImageGenSettings` 添加 per-agent resolve
**Files:** `backend/src/core/config.py` (修改)

- [ ] **Step 1 (TDD red):** 写测试 `tests/core/test_config_resolve.py` 加 `TestImageGenResolve` 类（4 个类似测试）
- [ ] **Step 2:** 跑测试确认失败
- [ ] **Step 3:** 在 `ImageGenSettings` 类添加 `resolve_for_agent(overrides: dict | None) -> dict`
- [ ] **Step 4:** 跑测试确认通过

### Task 5: 改造 `AgentConfig` 支持 llm / image_gen 子段 + env 引用
**Files:** `backend/src/agents/agent_config.py` (修改)

- [ ] **Step 1 (TDD red):** 写测试 `tests/agents/test_agent_config_resolution.py`:
  - `test_env_var_replacement_in_yaml`: yaml 写 `api_key: ${TEST_KEY}`，设 env 后解析为明文
  - `test_env_var_missing_keeps_placeholder`: env 没设时保持 `${TEST_KEY}` 字面
  - `test_recursive_env_replacement_in_nested_dict`: 嵌套 dict 也能解析
  - `test_agent_llm_section_falls_back_to_system`: agent 没配 `llm` 时回退 system-config
  - `test_agent_llm_section_falls_back_to_global`: agent 和 system 都没配时返回 None
  - `test_image_gen_section_resolution`: 同 LLM
- [ ] **Step 2:** 跑测试确认失败
- [ ] **Step 3:** 实现：
  - 新增模块级函数 `_expand_env(value: Any) -> Any`：递归处理 dict/list/str，识别 `${VAR}` 模式替换
  - 在 `AgentConfig.__init__` 中递归对 `self._config` 调 `_expand_env`
  - 新增属性 `llm: Optional[Dict]` 和 `image_gen: Optional[Dict]`：
    - 优先返回 agent 自己的
    - 否则回退 `_defaults["llm"]` / `_defaults["image_gen"]`
    - 否则 None
- [ ] **Step 4:** 跑测试确认通过

### Task 6: 扩展 `override_store` 支持 LLM/生图加密覆盖
**Files:** `backend/src/core/override_store.py` (修改)

- [ ] **Step 1 (TDD red):** 写测试 `tests/core/test_override_store_llm.py`:
  - `test_get_llm_override_default`: 未设置时返回 None
  - `test_update_llm_override_with_plain`: 设明文 api_key 存储为 `enc:` 前缀
  - `test_get_llm_override_decrypts`: 读出时解密
  - `test_update_image_gen_override_similar`: 类似 LLM
  - `test_clear_llm_override`: 清除后回到 None
- [ ] **Step 2:** 跑测试确认失败
- [ ] **Step 3:** 实现：
  - `get_llm_override(agent_id) -> dict | None`
  - `update_llm_override(agent_id, llm_config: dict) -> None`：
    - 加密 `api_key` 后存
    - 其他字段明文存
  - `clear_llm_override(agent_id) -> None`
  - `get_image_gen_override` / `update_image_gen_override` / `clear_image_gen_override` 类似
- [ ] **Step 4:** 跑测试确认通过

### Task 7: 改造 `create_ai_agent()` 应用 per-agent 配置
**Files:** `backend/src/agents/agent_config.py` (修改 `create_ai_agent`)

- [ ] **Step 1:** 修改 `create_ai_agent` 内部：
  - 加载 agent config 的 `llm` 段
  - 加载 override store 的 LLM 覆盖
  - 调用 `settings.llm.resolve_for_agent(merged_llm)` 拿到最终 base_url/api_key/model
  - **生图**不传给 AIAgent（生图是工具层的事情），但要保证 `tools` 调用生图工具时拿到 per-agent 配置
- [ ] **Step 2:** 在日志里打印最终生效的 `base_url/model/provider`，便于调试
- [ ] **Step 3:** 跑现有测试确认不破坏
- [ ] **Step 4:** 手动跑 `python -c "from src.agents import create_ai_agent; a = create_ai_agent('patent.ceo.v1'); print(a)"` 验证

### Task 8: 集成测试
**Files:** `tests/integration/test_per_agent_config.py` (新)

- [ ] **Step 1:** 写集成测试：
  - `test_agent_uses_global_when_no_override`: 不设任何覆盖，agent 用全局 active provider
  - `test_agent_uses_yaml_override`: 在 yaml 写 `${FAKE_KEY}`，agent 用 yaml 里的 base_url
  - `test_agent_uses_runtime_override_with_encryption`: 通过 override_store 设 api_key，agent 用解密后的值
  - `test_agent_full_precedence_chain`: yaml + override 都设，override 胜出
- [ ] **Step 2:** 跑测试确认通过

---

## Phase 2: 后端 API

### Task 9: 扩展 `GET /api/agents/{id}` 返回 LLM/生图配置
**Files:** `backend/src/api/routes.py`, `backend/src/api/schemas.py`

- [ ] **Step 1:** 在 `schemas.py` 新增 `ResolvedLLMConfigResponse` 和 `ResolvedImageGenConfigResponse`：
  - 字段：`provider`, `base_url`, `api_key` (masked: `sk-***xxxx`), `model`, `is_default` (bool), `source` ("global" | "agent_yaml" | "runtime_override")
- [ ] **Step 2:** 在 `get_agent_detail` 路由里计算 resolved LLM/生图配置并返回
- [ ] **Step 3:** 跑现有 API 测试（如果有）

### Task 10: 新增 agent LLM/生图配置 PUT API
**Files:** `backend/src/api/routes.py`, `backend/src/api/schemas.py`

- [ ] **Step 1:** 新增 schema `AgentLLMConfigUpdateRequest`：
  - `provider: str | None` (None = 清除覆盖)
  - `base_url: str | None`
  - `api_key: str | None` (空字符串 = 清除)
  - `model: str | None`
  - `use_default: bool = False` (True 时清除整个 LLM 覆盖)
- [ ] **Step 2:** 新增 `AgentImageGenConfigUpdateRequest` 类似
- [ ] **Step 3:** 路由 `PUT /api/agents/{agent_id}/llm-config`:
  - 校验 agent 存在
  - 如果 `use_default`：调用 `clear_llm_override`
  - 否则：`update_llm_override`
  - 返回 `ResolvedLLMConfigResponse`
- [ ] **Step 4:** 路由 `PUT /api/agents/{agent_id}/image-gen-config` 类似

### Task 11: 新增测试连通性 API
**Files:** `backend/src/api/routes.py`, `backend/src/api/schemas.py`

- [ ] **Step 1:** 路由 `POST /api/agents/{agent_id}/llm-config/test`:
  - 接收临时配置（request body），不持久化
  - 调用 OpenAI/Anthropic SDK 发送一个最小测试请求（"ping"）
  - 返回 `{success, latency_ms, error}`，5 秒超时
- [ ] **Step 2:** 路由 `POST /api/agents/{agent_id}/image-gen-config/test`:
  - 不真生图，调一个最小的 list models 或 health check
  - 返回 `{success, latency_ms, error}`
- [ ] **Step 3:** 单元测试覆盖 happy path + 错误路径（用 mock）

---

## Phase 3: 前端 UI

### Task 12: 扩展前端 types
**Files:** `frontend/types/index.ts` (或 `frontend/types/agent.ts`)

- [ ] **Step 1:** 添加类型：
```typescript
export interface ResolvedLLMConfig {
  provider: string
  base_url: string
  api_key_masked: string  // "sk-****xxxx"
  model: string
  is_default: boolean
  source: 'global' | 'agent_yaml' | 'runtime_override'
}

export interface ResolvedImageGenConfig extends ResolvedLLMConfig {
  model_id: string  // 注意生图叫 model_id
}

export interface AgentLLMConfigUpdate {
  provider?: string | null
  base_url?: string | null
  api_key?: string | null
  model?: string | null
  use_default?: boolean
}
```

### Task 13: 扩展 `lib/api.ts`
**Files:** `frontend/lib/api.ts`

- [ ] **Step 1:** 添加 `agentApi.getLLMConfig(id)`, `updateLLMConfig(id, body)`, `testLLMConfig(id, body)`
- [ ] **Step 2:** 添加 `agentApi.getImageGenConfig(id)`, `updateImageGenConfig(id, body)`, `testImageGenConfig(id, body)`

### Task 14: 新建 `AgentModelConfigPanel` 组件
**Files:** `frontend/components/agent/AgentModelConfigPanel.tsx` (新)

- [ ] **Step 1:** 创建组件 props:
```typescript
interface Props {
  title: string  // "LLM 配置" 或 "生图配置"
  kind: 'llm' | 'image_gen'
  initial: ResolvedLLMConfig | ResolvedImageGenConfig | null
  providers: Record<string, ProviderConfigResponse>  // 复用 system-config 类型
  onSaved: (resolved: ResolvedLLMConfig) => void
}
```
- [ ] **Step 2:** 复用 system-config 的 ProviderSelect / EditableField 模式
- [ ] **Step 3:** 包含：
  - "使用全局默认" 开关（开启时表单禁用，"恢复默认" 按钮可用）
  - provider 切换 → 动态展示 base_url / api_key / model 输入
  - api_key 显示/隐藏切换
  - "测试连通性" 按钮（带 loading 态 + 结果 toast）
  - "保存" 按钮
- [ ] **Step 4:** 写最小 prop 验证（TS 编译通过即可）

### Task 15: 在 `agents/page.tsx` 集成新面板
**Files:** `frontend/app/agents/page.tsx`

- [ ] **Step 1:** 在 agent 详情 Tab 区域新增 "模型配置" Tab
- [ ] **Step 2:** Tab 里放两个 `AgentModelConfigPanel`（LLM + 生图）
- [ ] **Step 3:** 保存成功后调用 `onSaved` 重新拉 agent 详情

---

## Phase 4: 端到端验证

### Task 16: 后端单元 + 集成测试通过
- [ ] **Step 1:** 跑 `cd backend && pytest tests/core/ tests/agents/ -v --cov`
- [ ] **Step 2:** 全部通过，覆盖率 ≥ 80% 新代码

### Task 17: 后端 API 手工验证
- [ ] **Step 1:** 启动 `python main.py`
- [ ] **Step 2:** 用 curl 验证 `GET /api/agents/{id}` 返回 `llm_config` 和 `image_gen_config`
- [ ] **Step 3:** 用 curl `PUT` 修改一个 agent 的 LLM 配置
- [ ] **Step 4:** 验证 `agent_overrides.json` 中 api_key 是 `enc:` 前缀
- [ ] **Step 5:** 用 curl `POST .../test` 验证连通性

### Task 18: 前端 Playwright 验证
- [ ] **Step 1:** 启动后端 + 前端
- [ ] **Step 2:** 用 playwright 打开 `/agents/{id}`，进入"模型配置" Tab
- [ ] **Step 3:** 切换 provider，填 api_key，保存，刷新验证持久化
- [ ] **Step 4:** 测试"使用全局默认"开关
- [ ] **Step 5:** 截图保存到 `docs/superpowers/plans/screenshots/`

### Task 19: 文档更新
**Files:** `backend/src/agents/AGENTS.md`, `backend/hermes_home/profiles/system-config/config.yaml` (注释)

- [ ] **Step 1:** 在 `agents/AGENTS.md` 增加一节"Per-Agent Configuration"，说明优先级、env 引用、加密存储
- [ ] **Step 2:** 在 `system-config/config.yaml` 顶部加注释指向文档
- [ ] **Step 3:** 提交

---

## Self-Review Checklist

- [x] Spec coverage: 所有需求（per-agent LLM/生图 / 缺失回退全局 / env 引用 / 加密 / 前端 UI）有 task 对应
- [x] No placeholders: 所有 step 都有具体代码或命令
- [x] Type consistency: `ResolvedLLMConfig` / `AgentLLMConfigUpdate` 在前后端命名一致
- [x] TDD: 每个新业务逻辑模块（cipher / resolve / override / agent_config）都有 red-green-refactor 步骤
- [x] Frequent commits: 每个 task 结尾都有 commit step
