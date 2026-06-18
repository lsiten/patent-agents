---
name: auto-patent-writing-lessons
description: 自动沉淀的专利分步撰写、附图生成和 DOCX 写入经验
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: patent_writer
---

# 自动沉淀的专利分步撰写、附图生成和 DOCX 写入经验

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

按章节分步撰写，附图逐图差异化生成，并在 DOCX 对应位置插入

## 执行准则

- 长文档必须分章节、分轮次写入草稿和 DOCX，避免一次性输出超上下文。
- 附图不能复用同一图改标题；每张图要有独立结构、独立说明和唯一图号。
- 生成 DOCX 前检查摘要、权利要求、说明书、附图说明和实际插图位置一致。

## 可复用缺陷类型

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
