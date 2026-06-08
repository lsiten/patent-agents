---
name: site-pattern-matching
description: 在访问复杂站点前先匹配 bundled web-access 的站点经验与已知陷阱
version: 1.0.0
metadata:
  tags: [site-patterns, browser, pitfalls, domain]
  agent: retrieval_analyst
---

# 站点经验匹配

当目标站点可能存在特定 URL 规则、反自动化行为或历史经验时优先使用。

## 操作要点

1. 先用 `web_access_match_site` 传入站点名、域名、平台名或任务描述
2. 如果命中站点经验，先吸收其中的有效模式、隐式参数和已知陷阱
3. 再决定后续使用 `web_access_read_page`、`web_access_find_url` 或 `web_access_browser`
4. 若未命中经验，不代表不可访问，按通用网页证据流程继续

## 典型场景

- 小红书、微信公众号等有反爬或特殊 URL 参数的网站
- 需要登录态、懒加载、动态渲染的平台
- 团队内部常访问、已有操作经验沉淀的站点
