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

## 可复用缺陷类型

- 摘要需包含专利名称、技术领域、简化方案和技术效果
- 权利要求需短句分行、独权3或4步、从权逐项限定
- 说明书需充分公开可实施细节并避免Markdown和交底噪声
- 附图需按当前专利内容逐图差异化生成并插入DOCX
- 最终DOCX路径、图片资源和下载可用性必须确认
- 检索报告需支撑区别特征和创造性论证
- 标题需清楚、简要且与技术主题一致

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略；禁止写入任务 ID、历史标题、历史附图标题、完整交底原文或用户隐私内容。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
