---
name: search-strategy
description: 设计高效的专利检索关键词和分类号组合
version: 1.0.0
metadata:
  tags: [检索策略, search, keywords, 关键词]
  agent: retrieval_analyst
---

# 检索策略制定

设计高效的专利检索关键词和分类号组合。

## 策略要素

1. **关键词选择** - 核心技术词、同义词、上下位词
2. **分类号组合** - IPC/CPC 分类号
3. **数据源选择** - CNIPA、USPTO、EPO、Google Patents

## 检索式构建

- 使用布尔运算符（AND、OR、NOT）
- 组合多个检索维度
- 逐步细化检索范围

## 工具使用

- `patent_search` - 执行专利检索
  - query: 检索关键词或技术描述
  - sources: cnipa,uspto,epo
  - limit: 最大结果数量
