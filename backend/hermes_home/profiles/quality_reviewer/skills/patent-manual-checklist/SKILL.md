---
name: patent-manual-checklist
description: 根据专利规范手册和问题分析报告审查申请文件，输出可路由修复的问题
version: 1.0.0
metadata:
  tags: [质量审查, 合规, 权利要求, 附图, 复审]
  agent: quality_reviewer
---

# 专利质量审查清单

## 必须判为 revise/reject 的问题

- 正文残留逐字稿时间戳、说话人或会议口语。
- 摘要缺少专利名称、技术领域、简化技术方案、技术效果任一要素，或超过 300 字。
- 权利要求1不是 3 步或 4 步。
- 权利要求中分号或句号后未换行。
- 从属权利要求引用自身、后序权利要求或缺少引用。
- 背景技术无真实现有技术引用，或泄露本发明方案。
- 附图说明与实际附图数量不一致。
- 正文引用了图号但没有对应附图文件。
- 多幅附图图片内容相同，或只是换标题。
- 出现重复图号或重复标题。
- 具体实施方式无法支持权利要求，或缺少必要实施例。

## 输出要求

每个问题必须包含：

- `severity`
- `location`
- `description`
- `suggestion`
- `target_agent`

`target_agent` 用于 CEO 调度修复，可选值包括：

- `requirement_analyst`
- `retrieval_analyst`
- `patent_writer`
- `quality_reviewer`
