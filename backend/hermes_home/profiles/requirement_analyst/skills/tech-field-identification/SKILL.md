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
