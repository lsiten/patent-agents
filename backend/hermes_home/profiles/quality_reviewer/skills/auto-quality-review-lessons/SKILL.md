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

## 最近样本

- ``：latest-quality-review-rules；状态 `unknown`。
- `5dd5c181-48d1-4e7d-aaed-c91bb3991166`：一种基于Cave折幕视频的处理方法及系统；状态 `failed`。
- `ea87620c-2db1-4fde-b05e-dd5d764cb77c`：这样我开个头！这个东西；状态 `failed`。
- `6eeed701-652a-48e5-aadd-126bffb11f20`：这样我开个头！这个东西；状态 `failed`，审查分 0.46。
  复用提醒：标题为空、具体实施方式截断、docx_path为空以及附图可访问性未确认，会导致提交文件不完整或形式审查补正。；核心算法和处理逻辑仍偏结果化，特别是映射关系、补充显示数据、过渡显示数据、裁剪边界和重映射参数缺少足够实施细节。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略，不把完整交底原文或用户隐私内容写入技能。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
