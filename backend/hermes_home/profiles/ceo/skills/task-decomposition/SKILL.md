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

需求分析完成 → 评估结果完整性和缺口
  → 缺少用户事实：dispatch brainstorm_partner 或回到对话确认
  → 缺少可检索证据/解决方案：dispatch retrieval_analyst
  → 完整且已确认：dispatch retrieval_analyst 进行正式检索

检索完成 → 将检索证据和风险反馈给 requirement_analyst 复核
  → 需求分析确认仍有缺口：按缺口继续 dispatch retrieval_analyst 或回到对话确认
  → 需求分析确认需求、证据、解决方案均已补齐：dispatch patent_writer

撰写完成 → dispatch quality_reviewer

审查完成 → 评估审查结果
  → 无 high/critical 问题且评分 ≥90分：交付用户
  → 不通过：按 responsible_phase 路由回 requirement_analyst / retrieval_analyst / patent_writer / 用户补充，修复后再次 dispatch quality_reviewer
```

## 工具使用

- `task_planner` - 制定工作计划和时间线
- `agent_selector` - 选择最适合的 Agent
