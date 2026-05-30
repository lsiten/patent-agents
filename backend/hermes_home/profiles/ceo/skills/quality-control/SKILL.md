---
name: quality-control
description: 评估每个阶段产出的质量，确保符合专利申请标准
version: 1.0.0
metadata:
  tags: [质量把控, 评估, quality, assessment]
  agent: ceo
---

# 质量把控

评估每个阶段产出的质量，确保符合专利申请标准。

## 质量不达标时的决策

| 问题类型 | 决策 |
|----------|------|
| 权利要求撰写质量差 | dispatch patent_writer 重写，附上具体修改意见 |
| 说明书与权利要求不一致 | dispatch patent_writer 修正，附上不一致点 |
| 保护范围过窄/过宽 | dispatch brainstorm_partner 重新讨论保护策略 |
| 缺少先有技术对比 | dispatch retrieval_analyst 补充检索 |
| 技术方案描述不清 | 直接问用户补充，或 dispatch brainstorm_partner |
| 形式问题（格式/编号） | dispatch patent_writer 修正，附上具体问题 |

## 工具使用

- `quality_assessor` - 对文件进行质量评估

## 迭代规则

- 最多迭代 3 轮（撰写→审查→修改）
- 超过 3 轮向用户报告困难
