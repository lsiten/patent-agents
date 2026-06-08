---
name: browser-source-reading
description: 对已知网页来源做快速阅读和证据摘录，补充非专利现有技术事实
version: 1.0.0
metadata:
  tags: [browser, reading, docs, product-pages]
  agent: retrieval_analyst
---

# 网页来源阅读

当你已经拿到明确 URL，需要读取页面内容并提炼事实时使用。

## 操作要点

1. 先用 `web_access_read_page` 读取页面正文
2. 提取标题、URL、发布日期、版本号、关键功能描述
3. 只保留和技术特征、公开时间、实现方式有关的证据
4. 如果正文缺失或内容依赖交互，再切到 `web_access_browser`

## 适用页面

- 官方文档
- 标准或规范页面
- 产品介绍页
- 帮助中心、发布说明、技术博客
