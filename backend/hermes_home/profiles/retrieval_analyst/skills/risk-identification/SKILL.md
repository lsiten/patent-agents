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
