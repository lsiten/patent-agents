---
name: risk-assessment
description: 识别和评估专利申请过程中的潜在风险
version: 1.0.0
metadata:
  tags: [风险评估, 风险识别, risk, assessment]
  agent: ceo
---

# 风险评估

识别和评估专利申请过程中的潜在风险。

## 检索不足时的决策

| 情况 | 决策 |
|------|------|
| 相关文献 < 3 篇 | dispatch retrieval_analyst 扩大检索范围 |
| 发现高度相似专利 | 告知用户风险，dispatch brainstorm_partner 讨论方案调整 |
| 检索方向偏移 | dispatch retrieval_analyst 重新检索，提供更精准关键词 |

## 工具使用

- `risk_analyzer` - 分析专利风险因素
