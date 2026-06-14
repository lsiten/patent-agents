---
name: tech-field-identification
description: 准确判断技术所属的 IPC 分类和技术领域
version: 1.0.0
metadata:
  tags: [技术领域, IPC, CPC, 分类]
  agent: requirement_analyst
---

# 技术领域识别

准确判断技术所属的 IPC 分类和技术领域。

## 识别流程

1. 分析技术描述的核心功能
2. 确定主要技术领域和次要领域
3. 匹配 IPC/CPC 分类号

## 工具使用

- `ipc_classifier` - 确定 IPC/CPC 分类号
  - 输入：tech_description
  - 输出：主分类号、次要分类号、置信度

## Agent 与工具边界

- `ipc_classifier` 只提供分类候选和置信度线索。
- 最终技术领域、主次领域、IPC/CPC 选择理由必须由需求分析 Agent 结合原始技术描述自行判断。
- 不得把工具返回的分类号原样当作最终结论；分类号和技术领域不一致时，以技术实质为准并说明不确定性。
