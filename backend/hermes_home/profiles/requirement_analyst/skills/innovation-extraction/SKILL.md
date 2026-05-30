---
name: innovation-extraction
description: 精准提炼技术方案的核心创新点和区别技术特征
version: 1.0.0
metadata:
  tags: [创新点, 技术特征, innovation, feature]
  agent: requirement_analyst
---

# 创新点提取

精准提炼技术方案的核心创新点和区别技术特征。

## 提取原则

- 创新点描述要具体、可验证，避免空泛表述
- 技术特征要全面，不遗漏任何可能有专利价值的细节
- 区分核心创新点和辅助特征

## 输出结构

```json
{
  "key_innovative_features": [
    {
      "feature_name": "特征名称",
      "description": "详细描述",
      "is_core": true,
      "technical_significance": "技术意义"
    }
  ]
}
```

## 工具使用

- `tech_feature_extractor` - 提取关键技术特征和创新点
