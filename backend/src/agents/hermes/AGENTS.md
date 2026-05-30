## hermes/ — Patent Tools Layer

### Architecture
保留 21 个专利工具实现 + adapter 桥接到 hermes-agent registry。
旧的 HermesAgent / Memory / Profiles 等已移除，由 `run_agent.AIAgent` 替代。

### File Map
| File | Role |
|------|------|
| `__init__.py` | 导出 `init_patent_tools()` |
| `base.py` | 工具基类: `HermesTool`, `HermesToolDefinition`, `make_tool_output()` |
| `tools/adapter.py` | 桥接层: 将 21 个工具注册到 hermes-agent registry |
| `tools/*.py` | 21 个专利工具实现 |

### Tool Output Standard
所有工具返回统一结构:
```python
{
    "tool": "patent_search",
    "success": True,
    "data": {...},          # 工具特定输出
    "timestamp": "...",
    "duration_ms": 123.4,
    "error": None           # 失败时填充
}
```

使用 `make_tool_output()` 辅助函数创建:
```python
from src.agents.hermes.base import make_tool_output

return make_tool_output(
    tool_name="patent_search",
    data={"patents": [...]},
    success=True,
    start_time=start_time
)
```

### Tool Registration Flow
```
init_patent_tools()
  ↓
adapter.py 遍历 21 个工具
  ↓
hermes_agent.registry.register_tool(name, definition, handler)
  ↓
AIAgent 实例化时自动加载 enabled_toolsets=["patent"]
```

### Tools List (21 total)
| Category | Tools |
|----------|-------|
| 搜索 | patent_search, web_search, knowledge_search |
| 分析 | tech_feature_extractor, ipc_classifier, novelty_analyzer |
| 规划 | task_planner, agent_selector |
| 调度 | dispatch_specialist |
| 质量 | quality_assessor, risk_analyzer |
| 生成 | report_generator, claim_writer, specification_writer |
| 数据 | patent_db_query, prior_art_finder |
| 其他 | ... |
