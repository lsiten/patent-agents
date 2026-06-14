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

## Agent 与工具边界

- `tech_feature_extractor` 只提供技术特征候选、关键词和可抽取线索。
- 核心创新点、区别技术特征、技术意义和保护价值必须由需求分析 Agent 结合原始沟通内容、上下文和专业知识自行判断。
- 不得把工具返回的候选列表原样作为最终 `key_innovative_features`；必须去重、合并、排序并标注核心/辅助关系。
- 对交底书、逐字稿、会议记录中的时间戳、说话人、口语化铺垫内容，只能用于理解技术含义，不能作为创新点文字直接输出。
