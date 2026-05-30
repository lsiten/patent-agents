---
name: novelty-assessment
description: 评估技术方案相对于现有技术的新颖性
version: 1.0.0
metadata:
  tags: [新颖性, novelty, 现有技术, prior art]
  agent: retrieval_analyst
---

# 新颖性评估

评估技术方案相对于现有技术的新颖性。

## 评估标准

新颖性要求技术方案不属于现有技术：
- 不存在相同的技术方案被公开
- 与最接近的现有技术存在区别技术特征

## 评估等级

| 等级 | 含义 |
|------|------|
| high | 未发现相同技术方案 |
| medium | 存在相似方案但有明显区别 |
| low | 存在高度相似的现有技术 |

## 输出结构

```json
{
  "novelty_assessment": {
    "rating": "high | medium | low",
    "rationale": "评估理由",
    "related_prior_art": ["相关对比文件"],
    "key_distinguishing_features": ["关键区别特征"]
  }
}
```
