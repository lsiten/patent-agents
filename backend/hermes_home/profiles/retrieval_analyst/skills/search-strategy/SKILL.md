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

## Agent 与工具边界

- `patent_search` 负责连接真实专利数据源并返回可核验证据；检索式设计、关键词取舍、数据库优先级和补检策略由检索分析 Agent 判断。
- 默认中国申请时，CNIPA 为第一顺位，USPTO/EPO/WIPO/Google Patents 只作为补充；其他法域按目标法域调整第一顺位。
- 数据源超时、未接入或无结果时，必须如实记录证据缺口，不得虚构专利号、申请人或公开日。
- 需要网页证据时，先完成专利检索主链路，再按 `web-evidence-strategy` 补充。
