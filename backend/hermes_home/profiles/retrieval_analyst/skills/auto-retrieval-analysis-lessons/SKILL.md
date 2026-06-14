---
name: auto-retrieval-analysis-lessons
description: 自动沉淀的专利检索关键词、检索策略和对比分析经验
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: retrieval_analyst
---

# 自动沉淀的专利检索关键词、检索策略和对比分析经验

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

围绕技术主题构造关键词、同义词和检索式，沉淀先有技术对比角度

## 执行准则

- 围绕主题拆分核心关键词、同义词、功能效果词和应用场景词，记录检索式与数据库来源。
- 检索报告要服务撰写：指出区别特征、可规避风险和需要强化的创新点。
- 检索过程和中间结果需要可展示，避免只给最终结论。

## 最近样本

- ``：latest-patent-retrieval-rules；状态 `unknown`。
- `5dd5c181-48d1-4e7d-aaed-c91bb3991166`：一种基于Cave折幕视频的处理方法及系统；状态 `failed`。
- `ea87620c-2db1-4fde-b05e-dd5d764cb77c`：这样我开个头！这个东西；状态 `failed`。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略，不把完整交底原文或用户隐私内容写入技能。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
