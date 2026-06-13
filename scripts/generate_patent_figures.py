#!/usr/bin/env python3
"""
Patent Figure Generator — 生成专利申请附图。

支持两种策略：
  1. matplotlib 绘制系统架构图 + 流程图（无需外部API）
  2. gen-img (gpt-image-2) AI 生成示意图（需 AI 配置）

AI 模式从环境变量读取配置：
  IMAGE_GEN_* > LLM_*

用法：
  # matplotlib 模式（默认）
  python generate_patent_figures.py --tech-desc "..." --output-dir ./figures

  # AI 模式（从当前环境读取 IMAGE_GEN_* 配置）
  python generate_patent_figures.py --tech-desc "..." --output-dir ./figures --ai

输出 JSON：
  [{"path": "...", "title": "...", "figure_number": 1}, ...]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _gen_img_script_path() -> Path:
    return (
        Path.home()
        / ".config" / "opencode" / "skills" / "gen-img" / "scripts" / "gen-img.mjs"
    )


def _has_image_generation_backend() -> bool:
    has_img_config = any(
        k.startswith("IMAGE_GEN_") and k.endswith("_API_KEY")
        for k in os.environ
    )
    has_llm_config = any(
        k.startswith("LLM_") and k.endswith("_API_KEY")
        for k in os.environ
    )
    return (has_img_config or has_llm_config) and _gen_img_script_path().exists()


# ═══════════════════════════════════════════════════════════════════
# Matplotlib 绘制
# ═══════════════════════════════════════════════════════════════════


def draw_matplotlib_figures(
    tech_description: str,
    output_dir: Path,
) -> List[Dict[str, str]]:
    """用 matplotlib 绘制系统架构图和流程图."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    # 中文字体
    plt.rcParams['font.sans-serif'] = [
        'Arial Unicode MS', 'Heiti SC', 'STHeiti',
        'SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei',
    ]
    plt.rcParams['axes.unicode_minus'] = False

    results: List[Dict[str, str]] = []

    # ── 图1: 系统架构图 ──
    keywords = re.findall(
        r'([\u4e00-\u9fff]{2,8}(?:系统|模块|装置|单元|组件|引擎|器|仪|机|传感器|设备))',
        tech_description,
    )
    keywords = list(dict.fromkeys(keywords))
    if not keywords:
        # 用前20个字打散作为占位
        raw = tech_description[:30]
        keywords = [raw[i:i+6] for i in range(0, len(raw), 6)][:6]

    fig, ax = plt.subplots(1, 1, figsize=(10, 7))
    ax.set_xlim(-1, 11)
    ax.set_ylim(-1, 9)
    ax.axis('off')
    ax.set_title("系统架构示意图", fontsize=14, fontweight='bold', pad=20)

    n = min(len(keywords), 8)
    cols = min(3, n)
    positions = []
    for i in range(n):
        row = i // cols
        col = i % cols
        x = 2 + col * 3.2
        y = 7 - row * 2.0
        positions.append((x, y))

    colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0', '#F3E5F5',
              '#E0F7FA', '#FFF8E1', '#FBE9E7', '#EFEBE9']
    edge_colors = ['#1E88E5', '#43A047', '#FB8C00', '#8E24AA',
                   '#00ACC1', '#FDD835', '#D84315', '#6D4C41']

    for i, (x, y) in enumerate(positions):
        box = FancyBboxPatch(
            (x - 1.2, y - 0.5), 2.4, 1.0,
            boxstyle="round,pad=0.08",
            facecolor=colors[i % len(colors)],
            edgecolor=edge_colors[i % len(edge_colors)],
            linewidth=1.5,
        )
        ax.add_patch(box)
        label = keywords[i] if i < len(keywords) else f"组件{i+1}"
        display = label[:6] + ("..." if len(label) > 6 else "")
        ax.text(x, y, display, ha='center', va='center',
                fontsize=9, fontweight='bold', color='#333333')

    # 连接箭头
    for i in range(len(positions) - 1):
        if abs(i - (i + 1)) <= cols:
            x1, y1 = positions[i]
            x2, y2 = positions[i + 1]
            ax.annotate(
                '', xy=(x2 - 1.2, y2), xytext=(x1 + 1.2, y1),
                arrowprops=dict(arrowstyle='->', color='#999999',
                                lw=1.0, connectionstyle='arc3,rad=0.15'),
            )

    path1 = str(output_dir / "figure_1_system_architecture.png")
    plt.tight_layout()
    plt.savefig(path1, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    results.append({"path": path1, "title": "系统架构示意图", "figure_number": 1})
    print(f"  ✓ 系统架构图: {path1}")

    # ── 图2: 方法流程图 ──
    steps = re.findall(
        r'([\u4e00-\u9fff]{4,20}(?:步骤|流程|方法|处理|计算|检测|获取|确定|'
        r'控制|调节|生成|判断|输出|输入|存储|发送|接收|识别|提取|转换|配置|'
        r'设置|更新))',
        tech_description,
    )
    steps = list(dict.fromkeys(steps))
    if not steps:
        steps = ["开始", "数据处理", "结果输出", "结束"]

    fig2, ax2 = plt.subplots(1, 1, figsize=(8, max(4, len(steps) * 1.6)))
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, max(4, len(steps) * 1.6 + 1))
    ax2.axis('off')
    ax2.set_title("方法流程图", fontsize=13, fontweight='bold', pad=15)

    x_center = 5
    y_start = max(3, len(steps) * 1.6)
    step_positions = []
    for i, step_text in enumerate(steps):
        y = y_start - i * 1.5
        display = step_text[:14] + ("..." if len(step_text) > 14 else "")
        box = FancyBboxPatch(
            (x_center - 1.8, y - 0.35), 3.6, 0.7,
            boxstyle="round,pad=0.06",
            facecolor='#E3F2FD', edgecolor='#1E88E5', linewidth=1.2,
        )
        ax2.add_patch(box)
        ax2.text(x_center, y, display, ha='center', va='center', fontsize=9)
        step_positions.append((x_center, y))

    for i in range(len(step_positions) - 1):
        x1, y1 = step_positions[i]
        x2, y2 = step_positions[i + 1]
        ax2.annotate(
            '', xy=(x2, y2 + 0.4), xytext=(x1, y1 - 0.4),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=1.2),
        )

    path2 = str(output_dir / "figure_2_method_flowchart.png")
    plt.tight_layout()
    plt.savefig(path2, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig2)
    results.append({"path": path2, "title": "方法流程图", "figure_number": 2})
    print(f"  ✓ 流程图: {path2}")

    return results


# ═══════════════════════════════════════════════════════════════════
# gen-img AI 生成
# ═══════════════════════════════════════════════════════════════════


def draw_ai_figures(
    tech_description: str,
    output_dir: Path,
) -> List[Dict[str, str]]:
    """通过 gen-img (gpt-image-2) 生成 AI 示意图.

    gen-img.mjs 会自动从环境变量读取 IMAGE_GEN_* / LLM_* / 旧版配置，
    无需在此手动传 api_key。
    """
    gen_img_script = _gen_img_script_path()
    if not gen_img_script.exists():
        return []

    results: List[Dict[str, str]] = []
    short_desc = tech_description[:200]

    # 直接传递当前环境，gen-img.mjs 内部会自行解析 IMAGE_GEN_* / LLM_* 等 vars
    env = os.environ

    # 图1: 系统架构图
    path1 = str(output_dir / "figure_1_architecture.png")
    prompt1 = (
        f"Patent system architecture diagram in clean black-and-white technical "
        f"drawing style, showing system components and their connections as block "
        f"diagram, Chinese labels, simple clear lines, white background, no shadows, "
        f"technical illustration style suitable for patent application. "
        f"System: {short_desc}"
    )
    try:
        r = subprocess.run(
            ["node", str(gen_img_script), "generate", prompt1,
             "--size", "1024x768", "--format", "png", "-o", path1],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if r.returncode == 0 and os.path.exists(path1):
            results.append({"path": path1, "title": "系统架构示意图 (AI)", "figure_number": 1})
            print(f"  ✓ AI 系统架构图: {path1}")
    except Exception as e:
        print(f"  ! AI 图1 失败: {e}", file=sys.stderr)

    # 图2: 方法流程图
    path2 = str(output_dir / "figure_2_flowchart.png")
    prompt2 = (
        f"Patent method flowchart in clean black-and-white technical drawing style, "
        f"showing process steps with arrows connecting them, Chinese labels, "
        f"simple clear boxes, white background, "
        f"technical illustration style suitable for patent application. "
        f"Method: {short_desc[:150]}"
    )
    try:
        r = subprocess.run(
            ["node", str(gen_img_script), "generate", prompt2,
             "--size", "768x1024", "--format", "png", "-o", path2],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if r.returncode == 0 and os.path.exists(path2):
            results.append({"path": path2, "title": "方法流程图 (AI)", "figure_number": 2})
            print(f"  ✓ AI 流程图: {path2}")
    except Exception as e:
        print(f"  ! AI 图2 失败: {e}", file=sys.stderr)

    return results


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Generate patent figures")
    parser.add_argument("--tech-desc", required=True, help="技术方案描述")
    parser.add_argument("--output-dir", default="./patent_figures", help="输出目录")
    parser.add_argument("--ai", action="store_true", help="优先使用 AI 生成")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"生成专利附图 → {output_dir}")

    if args.ai:
        # 检测 gen-img 可用性：IMAGE_GEN_* > LLM_*，脚本不存在时安静回退。
        if _has_image_generation_backend():
            print("\n[AI 模式]")
            results = draw_ai_figures(args.tech_desc, output_dir)
            if not results:
                print("  AI 生成无结果，回退到 matplotlib")
                results = draw_matplotlib_figures(args.tech_desc, output_dir)
        else:
            print("  未检测到可用 AI 生图后端，回退到 matplotlib")
            results = draw_matplotlib_figures(args.tech_desc, output_dir)
    else:
        print("\n[matplotlib 模式]")
        results = draw_matplotlib_figures(args.tech_desc, output_dir)

    print(f"\n共生成 {len(results)} 张图")
    for r in results:
        print(f"  图{r['figure_number']}: {r['title']} → {r['path']}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return results


if __name__ == "__main__":
    main()
