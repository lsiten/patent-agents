---
name: inventive-step-assessment
description: 评估技术方案的非显而易见性和创造性高度
version: 1.0.0
metadata:
  tags: [创造性, inventive step, 非显而易见性]
  agent: retrieval_analyst
---

# 创造性评估

评估技术方案的非显而易见性和创造性高度。

## 评估标准

创造性要求技术方案对本领域普通技术人员而言非显而易见：
- 技术效果是否预料不到
- 是否克服了技术偏见
- 是否解决了长期未解决的技术问题

## 三步法评估

1. 确定最接近的现有技术
2. 确定区别技术特征和实际解决的技术问题
3. 判断是否存在技术启示

## 输出结构

```json
{
  "inventive_step_assessment": {
    "rating": "high | medium | low",
    "rationale": "评估理由",
    "technical_effects": ["技术效果"],
    "obviousness_concerns": ["潜在显而易见性问题"]
  }
}
```

## 工具使用

- `patentability_scorer` - 评估专利性得分
