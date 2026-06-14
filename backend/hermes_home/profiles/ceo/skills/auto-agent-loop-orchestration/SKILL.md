---
name: auto-agent-loop-orchestration
description: 自动沉淀的专利 Agent Loop 调度、反馈闭环和终止条件经验
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: ceo
---

# 自动沉淀的专利 Agent Loop 调度、反馈闭环和终止条件经验

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

调度顺序、质量反馈闭环、终止条件与人工等待状态

## 执行准则

- 每次进入专利流程前，先明确 Done：质量审查可接受、关键问题清零、最终 DOCX 存在。
- 质量审查给出 revise/reject 或低分时，不结束流程；把具体问题传回对应 Agent 修复后再复审。
- 连续无进展或缺少用户信息时进入等待状态，并保留失败反馈供恢复后继续。

## 最近样本

历史失败样本不再作为调度参考加载。CEO 调度时只使用最新专利规范：

- Done 条件是质量审查可接受、硬规则问题清零、附图已生成并插入最终 DOCX。
- 任一阶段输出不符合最新结构，不做非最新结构兼容，必须调度对应 Agent 重写。
- 质量审查提出 revise/reject 时，把问题按目标 Agent 分派，修复后继续复审。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略，不把完整交底原文或用户隐私内容写入技能。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
