---
name: dynamic-page-evidence
description: 通过浏览器自动化读取动态、交互式或登录态页面中的补充证据
version: 1.0.0
metadata:
  tags: [dynamic-page, browser, login, evidence]
  agent: retrieval_analyst
---

# 动态页面取证

当页面依赖脚本执行、点击展开、滚动加载或登录态时使用。

## 操作要点

1. 用 `web_access_browser` 打开目标页面
2. 视需要执行导航、点击、滚动、读取页面信息、截图等操作
3. 只提取与公开时间、功能细节、技术实现、系统行为有关的事实
4. 页面可直接稳定访问后，再补用 `web_access_read_page` 做正文抽取

## 适用场景

- 单页应用或懒加载页面
- 登录后文档、控制台、演示环境
- 需要展开菜单、切换标签、触发交互后才能看到的内容
