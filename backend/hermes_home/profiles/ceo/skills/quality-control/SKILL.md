---
name: quality-control
description: 评估每个阶段产出的质量，确保符合专利申请标准
version: 1.0.0
metadata:
  tags: [质量把控, 评估, quality, assessment]
  agent: ceo
---

# 质量把控

评估每个阶段产出的质量，确保符合专利申请标准。

## 质量不达标时的决策

| 问题类型 | 决策 |
|----------|------|
| 权利要求撰写质量差 | dispatch patent_writer 重写，附上具体修改意见 |
| 说明书与权利要求不一致 | dispatch patent_writer 修正，附上不一致点 |
| 保护范围过窄/过宽 | dispatch brainstorm_partner 重新讨论保护策略 |
| 缺少先有技术对比 | dispatch retrieval_analyst 补充检索 |
| 技术方案描述不清 | 直接问用户补充，或 dispatch brainstorm_partner |
| 形式问题（格式/编号） | dispatch patent_writer 修正，附上具体问题 |

## 审查闭环

1. 撰写完成后必须调度 `quality_reviewer`。
2. 如果质量审查返回 `approve` 且关键问题可接受，才允许进入最终 DOCX 生成。
3. 如果质量审查返回 `revise`、`reject`、低分或存在 critical/high 问题，CEO 不能结束流程。
4. CEO 必须把审查 Agent 的问题完整传给对应 Agent 修复：
   - 需求不清 → `requirement_analyst` 或 `brainstorm_partner`
   - 现有技术/证据不足 → `retrieval_analyst`
   - 权利要求、说明书、摘要、附图、DOCX 插图问题 → `patent_writer`
   - 修复后 → 再次 `quality_reviewer`
5. 每一轮修复和复审结果都要保留，供前端以轮次/Tab 展示。
6. 只有确实缺少用户事实输入时，才进入等待补充信息；可由 Agent 专业判断或工具证据解决的问题不应要求用户填写。

## Done 条件

- 质量审查 Agent 判断 `recommendation=approve` 或整体达到可接受标准。
- critical/high 问题清零，或质量审查 Agent 明确说明剩余问题可接受。
- 所有正文引用的附图均存在、图号不重复、图片内容不重复且插入 DOCX 对应位置。
- 最终 DOCX 可生成、可下载、包含审查通过后的最新内容。

## 迭代规则

- 默认最多 3 轮“修复→复审”；超过 3 轮仍未达标时，向用户报告阻塞原因和下一步建议。
- 每轮必须携带上一轮失败反馈，禁止丢失审查意见后重新开始。
