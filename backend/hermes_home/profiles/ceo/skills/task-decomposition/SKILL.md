---
name: task-decomposition
description: 将复杂的专利申请任务分解为可执行的子任务，制定工作计划
version: 1.0.0
metadata:
  tags: [任务分解, 规划, planning, decomposition]
  agent: ceo
---

# 任务分解

将复杂的专利申请任务分解为可执行的子任务。

## 标准工作流程

```
用户描述技术 → 评估是否足够清晰
  → 不够清晰：追问 或 dispatch brainstorm_partner
  → 足够清晰：dispatch requirement_analyst

需求分析完成 → 评估结果完整性
  → 缺少关键信息：dispatch brainstorm_partner 补充
  → 完整：dispatch retrieval_analyst

检索完成 → 评估专利性
  → 风险过高：告知用户，建议调整
  → 可行：dispatch patent_writer

撰写完成 → dispatch quality_reviewer

审查完成 → 评估审查结果
  → 通过（≥80分）：交付用户
  → 不通过：分析原因，决定回退
```

## 工具使用

- `task_planner` - 制定工作计划和时间线
- `agent_selector` - 选择最适合的 Agent
