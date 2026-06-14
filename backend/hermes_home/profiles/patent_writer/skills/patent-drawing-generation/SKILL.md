---
name: patent-drawing-generation
description: 判断专利是否需要附图，调用生图工具生成中国专利风格附图，并维护图号、说明书引用和 DOCX 插图一致性
version: 1.0.0
metadata:
  tags: [附图, 生图, drawing, figure, docx]
  agent: patent_writer
---

# 专利附图生成

## 何时必须生成附图

当发明涉及以下任一内容时，必须生成说明书附图：
- 结构、装置、系统、模块连接关系
- 方法流程、控制流程、数据流、状态切换
- 空间关系、显示画面、投影边界、遮挡裁剪、补偿或重映射
- 多模块协同、端云协同、人机交互或硬件与软件组合

纯文字即可清楚公开的简单方法可以不生成附图，但必须在最终 JSON 中保持 `drawings` 为空数组，不要写占位内容。

## 工具调用

需要附图时，由专利撰写 Agent 调用 Hermes 工具：

```json
patent_drawing_generator(
  tech_description="专利整体技术方案背景，仅用于辅助理解",
  task_id="任务ID",
  title="该图在说明书中的附图标题",
  description="该图必须绘制的具体内容：包括图中对象、模块/步骤/结构、连接关系、箭头方向、编号和本图与其他图的区别",
  figure_number="图1"
)
```

每张图必须单独调用一次 `patent_drawing_generator`。如果附图说明引用图1、图2、图3，就必须生成三张图，不能用一张图替代多张图。
`description` 是必填的具体绘图输入，必须由当前专利真实内容决定；工具不会提供内置技术内容模板。

## 附图风格

- 使用中国专利说明书风格的黑白线稿、系统框图、流程图或结构示意图。
- 图中包含必要模块框、流程箭头、连接线和编号标记。
- 避免照片质感、装饰性背景、复杂颜色、营销式插画和无关元素。
- 每张图的内容必须对应其标题，不允许只是替换标题但图内结构重复。
- 不得把某个历史案例、示例主题或默认模板当成通用附图内容。

## 图号和正文一致性

- `drawings_data.figure_number`、附图说明、具体实施方式中的图号必须一致。
- 附图标题不能重复拼接图号或标题。
- 说明书中引用的每一个图号都必须有可访问的图片文件。
- 如果工具生成失败，不能把专利文档视为合格；应在最终 JSON 中返回可被质量审查识别的问题，等待 CEO 调度补图或修正。

## 输出字段

最终专利草稿 JSON 中的 `drawings` 应包含：

```json
[
  {
    "figure_number": "图1",
    "title": "当前专利真实附图标题",
    "description": "当前专利中本图需要表达的具体技术对象、关系、步骤或结构，不得只写泛化示意图名称。",
    "file_path": "/absolute/path/to/fig1.png",
    "artifact_url": "/api/v1/workflows/{task_id}/artifacts/draft/drawings/fig1.png",
    "mime_type": "image/png"
  }
]
```
