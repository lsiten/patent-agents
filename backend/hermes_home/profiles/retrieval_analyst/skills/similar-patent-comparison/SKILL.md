---
name: similar-patent-comparison
description: 对比分析最接近的现有技术，找出区别点
version: 1.0.0
metadata:
  tags: [相似专利, comparison, 对比分析]
  agent: retrieval_analyst
---

# 相似专利比对

对比分析最接近的现有技术，找出区别点。

## 比对要点

1. **相同技术特征** - 与现有技术相同的部分
2. **区别技术特征** - 与现有技术不同的部分
3. **技术效果差异** - 带来的不同技术效果

## 输出结构

```json
{
  "similar_patents": [
    {
      "patent_id": "CN112345678A",
      "title": "专利标题",
      "source": "CNIPA",
      "applicant": "申请人",
      "publication_date": "2023-01-15",
      "similarity_score": 0.85,
      "key_similarities": ["相似点"],
      "key_differences": ["区别点"],
      "risk_level": "high | medium | low"
    }
  ]
}
```

## 工具使用

- `similarity_analyzer` - 分析技术方案与现有专利的相似度

## Agent 与工具边界

- `similarity_analyzer` 返回的相似度只是候选排序依据。
- `key_similarities`、`key_differences` 和 `risk_level` 必须由检索分析 Agent 对照权利要求/摘要/说明书公开内容后判断。
- `similar_patents` 中每条记录必须来自真实检索结果，包含专利号、来源、申请人和公开日；缺失关键元数据时应降级为证据缺口而不是补造。
