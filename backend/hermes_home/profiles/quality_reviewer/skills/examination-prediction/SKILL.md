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

- `oa_predictor` - 提取可能触发审查意见的客观文本信号

## Agent 与工具边界

- `oa_predictor` 只提供可能审查意见的风险线索。
- 最终审查风险、通过建议、补正优先级和修改路径必须由质量审查 Agent 结合四个工具信号和自身审查经验判断。
- 如果问题可由撰写、检索或需求分析 Agent 修复，应在 `detailed_revision_suggestions` 中明确责任阶段，供 CEO 调度。
