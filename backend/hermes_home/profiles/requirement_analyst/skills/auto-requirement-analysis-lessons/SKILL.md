---
name: auto-requirement-analysis-lessons
description: 自动沉淀的交底/沟通内容清洗、主题识别和需求结构化经验
version: 1.0.0
enabled: true
metadata:
  tags:
    - auto-learned
    - patent
    - agent-loop
  generated_by: patent-agent-loop
  agent_profile: requirement_analyst
---

# 自动沉淀的交底/沟通内容清洗、主题识别和需求结构化经验

## 适用时机

当当前任务属于专利申请、专利检索、专利撰写、质量审查或流程调度时，优先参考本技能中的经验。

## 本轮沉淀重点

从逐字稿/沟通材料提炼技术主题，剔除口语化、时间戳和格式噪声

## 执行准则

- 逐字稿、聊天记录和交底材料只作为事实来源，不把时间戳、说话人、寒暄和格式噪声写入专利文本。
- 先提炼专利主题、技术问题、核心创新点、关键实施细节，再交给检索和撰写阶段。
- 信息不足时输出明确缺口，便于 CEO 调度头脑风暴或向用户追问。

## 最近样本

- ``：latest-requirement-analysis-rules；状态 `unknown`。
- `5dd5c181-48d1-4e7d-aaed-c91bb3991166`：一种基于Cave折幕视频的处理方法及系统；状态 `failed`。
- `ea87620c-2db1-4fde-b05e-dd5d764cb77c`：这样我开个头！这个东西；状态 `failed`。
- `6eeed701-652a-48e5-aadd-126bffb11f20`：这样我开个头！这个东西；状态 `failed`，审查分 0.46。
  复用提醒：标题为空、具体实施方式截断、docx_path为空以及附图可访问性未确认，会导致提交文件不完整或形式审查补正。；核心算法和处理逻辑仍偏结果化，特别是映射关系、补充显示数据、过渡显示数据、裁剪边界和重映射参数缺少足够实施细节。

## 使用要求

- 本技能是 Hermes profile-local skill，随对应 Agent 的 `HERMES_HOME` 加载。
- 只沉淀可复用方法、缺陷类型和修复策略，不把完整交底原文或用户隐私内容写入技能。
- 新一轮流程遇到相同缺陷时，先复用这里的修复策略，再调用工具或请求补充信息。
