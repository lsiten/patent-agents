---
name: transcript-to-patent-brief
description: 将交底逐字稿清洗并转化为专利方案确认卡，防止时间戳、说话人和口语内容进入专利文件
version: 1.0.0
metadata:
  tags: [逐字稿, 交底, 需求分析, 术语锁定]
  agent: requirement_analyst
---

# 逐字稿转专利方案

## 必须执行

1. 先调用 `transcript_sanitizer` 清洗逐字稿。
2. 从清洗后的技术事实中提炼专利主题，不得直接复制会议口语。
3. 输出 `approved_terms` 与 `forbidden_terms`：
   - `approved_terms`：可在全文统一使用的核心技术术语。
   - `forbidden_terms`：时间戳、说话人、会议口语、未经确认的自造抽象术语。
4. 输出 `claim_skeleton`，独权步骤数只能建议为 3 或 4。
5. 输出 `drawing_plan`，说明每幅图的目的、图号、对应权利要求或实施方式。

## 禁止

- 禁止把 `任(00:00:00)`、说话人姓名、会议记录格式写入专利方案。
- 禁止把“这个东西”“这样我开个头”等口语作为技术术语。
- 禁止在没有技术事实支撑时上推抽象概念。
