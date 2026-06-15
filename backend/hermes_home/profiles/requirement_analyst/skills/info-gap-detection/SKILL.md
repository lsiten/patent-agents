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

## 判断优先级

1. 先复核 `ipc_classifier`、`tech_feature_extractor`、`scenario_miner` 的返回内容，确认是否已经能支持判断。
2. 再结合专利代理经验和本领域常识补足可合理推断的信息。
3. 只有仍无法确定、且会影响保护主题、技术效果、实施方式或法域策略的信息，才列为 `information_gaps`。

## Agent 与工具边界

- 信息缺口是需求分析 Agent 的专业判断结果，不能由工具返回的空字段直接决定。
- 不要把工具已覆盖的信息重复要求用户补充。
- 缺口必须写成用户可回答的短句，并标注来源：`tool_signal_insufficient`、`knowledge_insufficient` 或 `genuinely_missing`。
