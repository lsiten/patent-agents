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

- ``：latest-agent-loop-orchestration-rules；状态 `unknown`。
- `5dd5c181-48d1-4e7d-aaed-c91bb3991166`：一种基于Cave折幕视频的处理方法及系统；状态 `failed`。
- `ea87620c-2db1-4fde-b05e-dd5d764cb77c`：这样我开个头！这个东西；状态 `failed`。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略，不把完整交底原文或用户隐私内容写入技能。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
