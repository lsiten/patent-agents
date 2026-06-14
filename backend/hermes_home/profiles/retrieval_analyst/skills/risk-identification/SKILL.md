---
name: risk-identification
description: 识别可能影响专利授权的潜在风险因素
version: 1.0.0
metadata:
  tags: [风险识别, risk, 驳回风险]
  agent: retrieval_analyst
---

# 风险因素识别

识别可能影响专利授权的潜在风险因素。

## 风险类型

| 风险类型 | 说明 |
|----------|------|
| 新颖性风险 | 存在相同现有技术 |
| 创造性风险 | 技术方案显而易见 |
| 支持性风险 | 权利要求得不到支持 |
| 公开不充分风险 | 说明书公开不充分 |

## 输出结构

```json
{
  "risk_factors": [
    {
      "risk_type": "风险类型",
      "description": "风险描述",
      "severity": "critical | high | medium | low",
      "mitigation": "缓解建议"
    }
  ]
}
```

## 工具使用

- `risk_analyzer` - 分析专利风险因素

## Agent 与工具边界

- `risk_analyzer` 只提供风险线索和客观命中项。
- 风险类型、严重程度、优先级和缓解建议必须由检索分析 Agent 结合新颖性、创造性、支持性和撰写策略综合判断。
- 如果风险来自证据不足，应标注为 `evidence_missing` 类问题，不要伪装成确定驳回风险。
