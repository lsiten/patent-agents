---
name: web-evidence-strategy
description: 将网页访问作为专利检索后的补充证据通道，优先选择可核验来源
version: 1.0.0
metadata:
  tags: [web, evidence, 官方资料, prior-art]
  agent: retrieval_analyst
---

# 网页证据策略

在专利工具主链路完成后，再决定是否补充网页证据。

## 优先来源

1. 官方文档、标准规范、帮助中心、开发者文档
2. 产品页面、版本说明、发布公告、白皮书
3. 公开可核验的非专利现有技术页面

## 使用原则

- 先用 `patent_search` 锁定专利现有技术，再用网页来源补足背景事实
- 优先用 `web_access_read_page` 读取已知 URL
- 不知道入口时，先用 `web_access_find_url` 定位站点
- 页面需要脚本、点击、登录时，再改用 `web_access_browser`
- 记录 URL、标题、发布日期或版本号、关键摘录
- 网页证据只补充专利工具链路，不替代 `patent_search`、`similarity_analyzer`、`patentability_scorer` 和 `risk_analyzer`。
- 网页事实不能直接写成专利性结论；最终新颖性、创造性和风险结论仍由检索分析 Agent 判断。
