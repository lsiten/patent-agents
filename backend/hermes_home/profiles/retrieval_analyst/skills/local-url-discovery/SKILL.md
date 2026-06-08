---
name: local-url-discovery
description: 从本地浏览历史和书签中定位内部站点、历史来源或已访问资料页
version: 1.0.0
metadata:
  tags: [local, url, history, bookmarks]
  agent: retrieval_analyst
---

# 本地 URL 发现

当目标站点可能是内部页面、合作方页面，或你只记得大致名称时使用。

## 操作要点

1. 用 `web_access_find_url` 结合站点名、系统名、品牌名查找候选 URL
2. 优先选择标题清晰、路径稳定、与任务最相关的结果
3. 找到 URL 后，公开页面用 `web_access_read_page`，动态页面用 `web_access_browser`
4. 不能把历史记录命中直接当作证据，必须继续打开页面确认内容

## 典型场景

- 内部知识库或后台系统
- 之前访问过的产品文档
- 收藏在书签里的标准、白皮书、合作站点
