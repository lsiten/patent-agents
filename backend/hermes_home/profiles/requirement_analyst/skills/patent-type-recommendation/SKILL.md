---
name: patent-type-recommendation
description: 基于技术特征建议最合适的专利保护类型
version: 1.0.0
metadata:
  tags: [专利类型, invention, utility_model, 发明, 实用新型]
  agent: requirement_analyst
---

# 专利类型建议

基于技术特征建议最合适的专利保护类型。

## 专利类型

| 类型 | 适用场景 | 保护期限 |
|------|----------|----------|
| 发明专利 | 有创造性的技术方案 | 20年 |
| 实用新型 | 产品形状/结构改进 | 10年 |
| 外观设计 | 产品外观设计 | 15年 |

## 判断因素

1. 技术创新程度
2. 保护需求紧迫性
3. 技术方案类型（方法/产品）
4. 市场竞争状况

## 输出结构

```json
{
  "patent_type_recommendation": {
    "suggested_type": "invention | utility_model",
    "rationale": "推荐理由",
    "confidence": 0.85
  }
}
```
