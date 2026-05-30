---
name: info-gap-detection
description: 发现技术描述中的缺失信息，提出补充要求
version: 1.0.0
metadata:
  tags: [信息缺口, gap, 补充信息]
  agent: requirement_analyst
---

# 信息缺口识别

发现技术描述中的缺失信息，提出补充要求。

## 检查要点

1. 技术原理是否清楚
2. 实现步骤是否完整
3. 关键参数是否提供
4. 与现有技术的区别是否明确

## 输出结构

```json
{
  "information_gaps": [
    {
      "gap": "信息缺口描述",
      "importance": "high | medium | low",
      "suggestion": "补充建议"
    }
  ]
}
```

## 处理方式

- 高重要性缺口：必须补充后才能继续
- 中重要性缺口：建议补充，可先行分析
- 低重要性缺口：可选补充
