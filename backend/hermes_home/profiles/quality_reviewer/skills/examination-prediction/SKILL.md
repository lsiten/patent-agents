---
name: examination-prediction
description: 预判审查员可能提出的审查意见
version: 1.0.0
metadata:
  tags: [审查意见预判, OA, examination, prediction]
  agent: quality_reviewer
---

# 审查意见预判

预判审查员可能提出的审查意见。

## 预判维度

1. **新颖性审查意见** - 可能引用的对比文件
2. **创造性审查意见** - 可能的显而易见性质疑
3. **清楚性审查意见** - 可能的表述不清问题
4. **支持性审查意见** - 可能的超范围问题

## 输出结构

```json
{
  "examination_risks": [
    {
      "risk_type": "风险类型",
      "likelihood": "high | medium | low",
      "description": "风险描述",
      "mitigation_suggestion": "缓解建议"
    }
  ]
}
```

## 工具使用

- `oa_predictor` - 预判审查意见
