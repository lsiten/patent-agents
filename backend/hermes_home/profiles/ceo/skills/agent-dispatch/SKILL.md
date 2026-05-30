---
name: agent-dispatch
description: 根据任务性质选择和调度合适的专业 Agent，将具体工作派发给专业 Agent 执行
version: 1.0.0
metadata:
  tags: [调度, 分配, 指派, schedule, assign]
  agent: ceo
---

# Agent 调度

根据任务性质选择和调度合适的专业 Agent。

## 可调度的专业 Agent

| Agent ID | 专长 | 何时调用 |
|----------|------|----------|
| `brainstorm_partner` | 技术讨论、思路发散、方向探索 | 技术方案模糊、需要用户补充、需要拓展保护范围时 |
| `requirement_analyst` | 需求结构化、创新点提取、IPC分类 | 技术方案明确后，需要结构化分析时 |
| `retrieval_analyst` | 先有技术检索、专利性评估、风险识别 | 有了结构化需求后，需要评估新颖性/创造性时 |
| `patent_writer` | 撰写权利要求、说明书、摘要 | 检索通过后，需要撰写正式文件时 |
| `quality_reviewer` | 形式审查、实质审查、一致性检查 | 文件撰写完成后，需要质量把关时 |

## 调度工具

使用 `dispatch_specialist` 工具将任务派发给专业 Agent：

```
dispatch_specialist(
  agent_id="<agent_id>",
  task="<具体任务描述>",
  context="<附加上下文>"
)
```

## 调度原则

1. 每次只调度一个 Agent
2. 任务描述要清晰完整，包含所有必要上下文
3. 调度后评估结果，不盲目推进
4. 发现质量问题时主动回退
