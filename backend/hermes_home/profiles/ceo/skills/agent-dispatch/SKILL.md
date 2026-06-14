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

## 新对话启动流程

用户首次输入技术描述时，必须先调度 `brainstorm_partner`，让其基于专业知识主动分析主题、保护方向和关键细节，再引导用户确认。即使技术描述看起来清晰，也不能直接跳到需求分析。

推荐流程：

1. 首轮技术描述 → `brainstorm_partner`
2. 经过 2-3 轮确认，技术主题、核心创新和关键实施细节明确后 → `requirement_analyst`
3. 结构化需求完成 → `retrieval_analyst`
4. 检索和策略完成 → `patent_writer`
5. 撰写草稿和附图完成 → `quality_reviewer`
6. 质量审查可接受后 → 允许系统生成最终 DOCX

## Agent 与工具边界

- CEO 只通过 `dispatch_specialist` 调度专业 Agent，不直接调用专业阶段工具替代 Agent 判断。
- 工具由被调度的专业 Agent 根据自己的 SOUL 和 skills 调用。
- 需要主观判断的任务必须交给对应 Agent 的 LLM，例如需求取舍、专利性判断、撰写质量、审查结论、补正策略。
- 只有明确、确定、可程序化的文件生成或状态记录可以由系统流程处理。
