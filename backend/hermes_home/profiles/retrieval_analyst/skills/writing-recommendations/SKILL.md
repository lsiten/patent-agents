---
name: writing-recommendations
description: 基于检索结果为撰写环节提供策略建议
version: 1.0.0
metadata:
  tags: [撰写建议, recommendations, 策略]
  agent: retrieval_analyst
---

# 撰写建议生成

基于检索结果为撰写环节提供策略建议。

## 建议维度

1. **保护范围建议** - 独立权利要求的保护范围
2. **区别特征强调** - 需要重点突出的区别点
3. **规避策略** - 如何规避现有技术
4. **布局建议** - 从属权利要求的布局

## 输出结构

```json
{
  "writing_recommendations": [
    {
      "focus_area": "重点关注领域",
      "recommendation": "具体建议",
      "priority": "high | medium | low"
    }
  ]
}
```

## 原则

- 建议要具体、可操作
- 能直接指导后续撰写工作
- 结合检索到的对比文件给出针对性建议
