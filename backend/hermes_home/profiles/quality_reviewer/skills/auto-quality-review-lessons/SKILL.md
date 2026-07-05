---
name: auto-quality-review-lessons
description: 自动沉淀的专利质量审查、附图审查和复审闭环经验
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: quality_reviewer
---

# 自动沉淀的专利质量审查、附图审查和复审闭环经验

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

同时审查文本、权利要求、说明书一致性、附图缺失/重复和 DOCX 可用性

## 执行准则

- 审查不只看文本合规，还要检查附图是否缺失、重复、图号重复、说明与正文是否一致。
- 发现问题时输出可调度的缺陷清单：归属 Agent、严重级别、修复建议和复审条件。
- 只有关键问题可接受且最终 DOCX 可下载时才允许通过。

## 可复用缺陷类型

- 本轮未沉淀可复用缺陷类型。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略；禁止写入任务 ID、历史标题、历史附图标题、完整交底原文或用户隐私内容。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
