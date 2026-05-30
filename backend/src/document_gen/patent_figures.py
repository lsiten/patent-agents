"""
Patent Figure Generator — 根据 LLM 生成的图表描述绘制专利附图。

支持的图表类型：
1. system_architecture: 系统架构图（模块框图 + 箭头连接）
2. flowchart: 方法流程图（步骤框 + 判断菱形 + 箭头）

输出格式：PNG 图片文件，适合嵌入 DOCX。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')  # 非交互后端
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

from loguru import logger


# ─── 中文字体配置 ─────────────────────────────────────────────────────────────

def _configure_chinese_font():
    """配置 matplotlib 支持中文。"""
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti SC', 'STHeiti', 'SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False


_configure_chinese_font()


# ─── 系统架构图 ──────────────────────────────────────────────────────────────

def draw_system_architecture(
    modules: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
    title: str = "",
    output_path: Optional[str] = None,
) -> str:
    """
    绘制系统架构图。

    Args:
        modules: [{"name": "模块名", "description": "描述", "x": 0, "y": 0}]
        connections: [{"from": "模块A", "to": "模块B", "label": "数据流"}]
        title: 图标题
        output_path: 输出路径

    Returns:
        生成的图片文件路径
    """
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    ax.set_xlim(-1, 11)
    ax.set_ylim(-1, 9)
    ax.axis('off')

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

    # 计算模块位置（如果未提供坐标，自动布局）
    n = len(modules)
    if not modules or not modules[0].get('x') and not modules[0].get('y'):
        # 自动网格布局
        cols = min(3, n)
        rows = (n + cols - 1) // cols
        for i, mod in enumerate(modules):
            row = i // cols
            col = i % cols
            mod['x'] = 2 + col * 3.5
            mod['y'] = 7 - row * 2.5

    # 绘制模块框
    module_positions = {}
    for mod in modules:
        x, y = mod.get('x', 5), mod.get('y', 5)
        name = mod.get('name', '')
        desc = mod.get('description', '')

        # 绘制圆角矩形
        box = FancyBboxPatch(
            (x - 1.2, y - 0.6), 2.4, 1.2,
            boxstyle="round,pad=0.1",
            facecolor='#E8F4FD',
            edgecolor='#2196F3',
            linewidth=1.5,
        )
        ax.add_patch(box)

        # 模块名称
        ax.text(x, y + 0.1, name, ha='center', va='center',
                fontsize=10, fontweight='bold', color='#1565C0')

        # 简短描述
        if desc:
            short_desc = desc[:12] + '...' if len(desc) > 12 else desc
            ax.text(x, y - 0.3, short_desc, ha='center', va='center',
                    fontsize=7, color='#666666')

        module_positions[name] = (x, y)

    # 绘制连接箭头
    for conn in connections:
        from_name = conn.get('from', '')
        to_name = conn.get('to', '')
        label = conn.get('label', '')

        if from_name in module_positions and to_name in module_positions:
            x1, y1 = module_positions[from_name]
            x2, y2 = module_positions[to_name]

            # 计算箭头起止点（从框边缘出发）
            dx = x2 - x1
            dy = y2 - y1
            dist = np.sqrt(dx**2 + dy**2)
            if dist > 0:
                # 从框边缘出发
                offset = 0.7
                sx = x1 + offset * dx / dist
                sy = y1 + offset * dy / dist
                ex = x2 - offset * dx / dist
                ey = y2 - offset * dy / dist

                ax.annotate(
                    '', xy=(ex, ey), xytext=(sx, sy),
                    arrowprops=dict(
                        arrowstyle='->', color='#666666',
                        lw=1.2, connectionstyle='arc3,rad=0.1'
                    )
                )

                # 连接标签
                if label:
                    mx = (sx + ex) / 2
                    my = (sy + ey) / 2
                    ax.text(mx, my + 0.2, label, ha='center', va='center',
                            fontsize=7, color='#999999',
                            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.8))

    plt.tight_layout()

    if not output_path:
        output_path = '/tmp/patent_architecture.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    logger.info(f"系统架构图已生成: {output_path}")
    return output_path


# ─── 方法流程图 ──────────────────────────────────────────────────────────────

def draw_flowchart(
    steps: List[Dict[str, Any]],
    title: str = "",
    output_path: Optional[str] = None,
) -> str:
    """
    绘制方法流程图。

    Args:
        steps: [{"text": "步骤描述", "type": "process|decision|start|end"}]
        title: 图标题
        output_path: 输出路径

    Returns:
        生成的图片文件路径
    """
    n = len(steps)
    fig_height = max(6, n * 1.8 + 2)
    fig, ax = plt.subplots(1, 1, figsize=(8, fig_height))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_height)
    ax.axis('off')

    if title:
        ax.set_title(title, fontsize=13, fontweight='bold', pad=15)

    # 从上到下布局
    x_center = 5
    y_start = fig_height - 1.5
    y_gap = 1.6
    step_positions = []

    for i, step in enumerate(steps):
        y = y_start - i * y_gap
        step_type = step.get('type', 'process')
        text = step.get('text', f'步骤{i+1}')

        # 截断过长文本
        if len(text) > 20:
            text = text[:18] + '...'

        if step_type == 'start' or step_type == 'end':
            # 椭圆形
            ellipse = mpatches.Ellipse(
                (x_center, y), 3.0, 0.9,
                facecolor='#C8E6C9' if step_type == 'start' else '#FFCDD2',
                edgecolor='#4CAF50' if step_type == 'start' else '#F44336',
                linewidth=1.5,
            )
            ax.add_patch(ellipse)
            ax.text(x_center, y, text, ha='center', va='center',
                    fontsize=9, fontweight='bold')

        elif step_type == 'decision':
            # 菱形
            diamond = plt.Polygon(
                [(x_center, y + 0.5), (x_center + 1.8, y),
                 (x_center, y - 0.5), (x_center - 1.8, y)],
                facecolor='#FFF9C4', edgecolor='#FFC107', linewidth=1.5,
            )
            ax.add_patch(diamond)
            ax.text(x_center, y, text, ha='center', va='center',
                    fontsize=8, fontweight='bold')

        else:
            # 矩形（普通步骤）
            box = FancyBboxPatch(
                (x_center - 1.8, y - 0.4), 3.6, 0.8,
                boxstyle="round,pad=0.08",
                facecolor='#E3F2FD',
                edgecolor='#2196F3',
                linewidth=1.2,
            )
            ax.add_patch(box)
            ax.text(x_center, y, text, ha='center', va='center',
                    fontsize=9)

        step_positions.append((x_center, y))

    # 绘制步骤之间的箭头
    for i in range(len(step_positions) - 1):
        x1, y1 = step_positions[i]
        x2, y2 = step_positions[i + 1]
        ax.annotate(
            '', xy=(x2, y2 + 0.45), xytext=(x1, y1 - 0.45),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=1.2)
        )

    plt.tight_layout()

    if not output_path:
        output_path = '/tmp/patent_flowchart.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    logger.info(f"流程图已生成: {output_path}")
    return output_path


# ─── 主入口：根据 LLM 输出生成附图 ─────────────────────────────────────────────

def generate_patent_figures(
    figure_specs: List[Dict[str, Any]],
    task_id: str,
    output_dir: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """
    根据 LLM 生成的图表规格绘制所有专利附图。

    Args:
        figure_specs: LLM 输出的图表描述列表，每个包含:
            - type: "system_architecture" | "flowchart"
            - title: 图表标题
            - data: 图表数据（modules/connections 或 steps）
        task_id: 任务 ID
        output_dir: 输出目录

    Returns:
        生成的图片信息列表 [{"path": "...", "title": "...", "figure_number": 1}]
    """
    if output_dir is None:
        output_dir = Path("./exports") / task_id / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for i, spec in enumerate(figure_specs, 1):
        fig_type = spec.get('type', 'flowchart')
        title = spec.get('title', f'图{i}')
        data = spec.get('data', {})
        output_path = str(output_dir / f"figure_{i}.png")

        try:
            if fig_type == 'system_architecture':
                modules = data.get('modules', [])
                connections = data.get('connections', [])
                draw_system_architecture(modules, connections, title=title, output_path=output_path)
            elif fig_type == 'flowchart':
                steps = data.get('steps', [])
                draw_flowchart(steps, title=title, output_path=output_path)
            else:
                logger.warning(f"Unknown figure type: {fig_type}, skipping")
                continue

            results.append({
                "path": output_path,
                "title": title,
                "figure_number": i,
            })
        except Exception as e:
            logger.error(f"Failed to generate figure {i}: {e}")

    return results
