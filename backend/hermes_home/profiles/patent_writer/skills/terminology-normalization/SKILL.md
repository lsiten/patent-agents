---
name: terminology-normalization
description: 规范专利文件中的技术术语，确保全文一致性和专业性
version: 1.0.0
metadata:
  tags: [术语, terminology, 规范化, 一致性]
  agent: patent_writer
---

# 技术术语规范化

规范专利文件中的技术术语，确保全文一致性和专业性。

## 规范原则

1. 同一技术特征全文使用完全相同的名称
2. 不得出现名称变换（简写、缩写、同义替换）
3. 首次出现的术语需要定义说明
4. 使用本领域公认的标准术语

## 常见问题

- ❌ 错误：模型 → 该模型 → 预测模型（名称不一致）
- ✅ 正确：预测模型 → 所述预测模型（统一命名）

## 工具使用

- `terminology_normalizer` - 规范化文本中的技术术语
