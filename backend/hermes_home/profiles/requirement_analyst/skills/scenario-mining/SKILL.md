---
name: scenario-mining
description: 发现技术发明的潜在应用场景和扩展领域
version: 1.0.0
metadata:
  tags: [应用场景, scenario, 市场价值]
  agent: requirement_analyst
---

# 应用场景挖掘

发现技术发明的潜在应用场景和扩展领域。

## 挖掘维度

1. **直接应用场景** - 技术方案最直接的使用场景
2. **扩展应用场景** - 技术可以延伸的其他领域
3. **商业价值评估** - 每个场景的市场潜力

## 输出结构

```json
{
  "application_scenarios": [
    {
      "scenario": "应用场景描述",
      "potential_value": "专利价值评估",
      "confidence": 0.8
    }
  ]
}
```

## 工具使用

- `scenario_miner` - 挖掘潜在应用场景
