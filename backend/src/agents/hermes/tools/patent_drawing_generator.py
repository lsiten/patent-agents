"""Patent drawing generation tool using project image/LLM configuration."""

from __future__ import annotations

import base64
import html
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.agents.hermes.base import make_tool_output
from src.core.config import settings


def _generate_image_file(prompt: str, output_path: Path, image_config: Dict[str, Any]) -> None:
    """Generate one image through an OpenAI-compatible image endpoint."""
    api_key = str(image_config.get("api_key") or "")
    base_url = str(image_config.get("base_url") or "").rstrip("/")
    model_id = str(image_config.get("model_id") or "gpt-image-2")

    if not api_key:
        raise RuntimeError("Image generation API key is not configured")
    if not base_url:
        raise RuntimeError("Image generation base_url is not configured")

    endpoint = base_url if base_url.endswith("/images/generations") else f"{base_url}/images/generations"
    payload = json.dumps(
        {
            "model": model_id,
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode("utf-8"))

    image_data = (body.get("data") or [{}])[0]
    b64_json = image_data.get("b64_json")
    if b64_json:
        output_path.write_bytes(base64.b64decode(b64_json))
        return

    image_url = image_data.get("url")
    if image_url:
        with urllib.request.urlopen(image_url, timeout=180) as response:
            output_path.write_bytes(response.read())
        return

    raise RuntimeError("Image generation response did not include b64_json or url")


def _resolve_image_config(profile_id: str = "patent.writer.v1") -> Dict[str, Any]:
    """Resolve image config with agent overrides taking precedence over system config."""
    image_overrides: Dict[str, Any] = {}

    try:
        from src.agents.agent_config import get_agent_config

        agent_config = get_agent_config(profile_id)
        if agent_config:
            image_overrides.update(agent_config.image_gen or {})
    except Exception:
        image_overrides = {}

    try:
        from src.core.override_store import get_override_store

        runtime_override = get_override_store().get_image_gen_override(profile_id) or {}
        image_overrides.update(runtime_override)
    except Exception:
        pass

    return settings.image_gen.resolve_for_agent(image_overrides)


def _safe_figure_filename(figure_number: str) -> str:
    digits = "".join(ch for ch in str(figure_number or "") if ch.isdigit())
    return f"fig{digits or '1'}.png"


def _write_fallback_png(output_path: Path, title: str, tech_description: str, figure_number: str) -> None:
    """Write a local line-art PNG so generated DOCX files can embed it."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise RuntimeError("Pillow is required for fallback PNG generation") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 820), "white")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("Arial Unicode.ttf", 30)
        body_font = ImageFont.truetype("Arial Unicode.ttf", 22)
        small_font = ImageFont.truetype("Arial Unicode.ttf", 18)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    def safe_text(x: int, y: int, text: str, font: Any, anchor: str = "lt") -> None:
        try:
            if anchor == "center":
                bbox = draw.textbbox((0, 0), text, font=font)
                draw.text((x - (bbox[2] - bbox[0]) / 2, y), text, fill="black", font=font)
            else:
                draw.text((x, y), text, fill="black", font=font)
        except UnicodeEncodeError:
            fallback = "Patent Figure"
            if anchor == "center":
                bbox = draw.textbbox((0, 0), fallback, font=font)
                draw.text((x - (bbox[2] - bbox[0]) / 2, y), fallback, fill="black", font=font)
            else:
                draw.text((x, y), fallback, fill="black", font=font)

    def center_text(x: int, y: int, text: str, font: Any) -> None:
        safe_text(x, y, text, font, anchor="center")

    def box(x1: int, y1: int, x2: int, y2: int, label: str, font: Any = body_font) -> None:
        draw.rectangle((x1, y1, x2, y2), outline="black", width=3)
        center_text((x1 + x2) // 2, (y1 + y2) // 2 - 10, label, font)

    def arrow(start: tuple[int, int], end: tuple[int, int], width: int = 3) -> None:
        draw.line([start, end], fill="black", width=width)
        dx = 1 if end[0] >= start[0] else -1
        dy = 1 if end[1] >= start[1] else -1
        draw.polygon(
            [(end[0], end[1]), (end[0] - dx * 14, end[1] - dy * 6), (end[0] - dx * 6, end[1] - dy * 14)],
            fill="black",
        )

    def dashed_rect(rect: tuple[int, int, int, int], label: str) -> None:
        x1, y1, x2, y2 = rect
        dash = 18
        for x in range(x1, x2, dash * 2):
            draw.line([(x, y1), (min(x + dash, x2), y1)], fill="black", width=2)
            draw.line([(x, y2), (min(x + dash, x2), y2)], fill="black", width=2)
        for y in range(y1, y2, dash * 2):
            draw.line([(x1, y), (x1, min(y + dash, y2))], fill="black", width=2)
            draw.line([(x2, y), (x2, min(y + dash, y2))], fill="black", width=2)
        center_text((x1 + x2) // 2, y2 + 12, label, small_font)

    def rotated_quad(points: list[tuple[int, int]], label: str) -> None:
        draw.polygon(points, outline="black", fill="white")
        draw.line(points + [points[0]], fill="black", width=3)
        cx = sum(x for x, _ in points) // len(points)
        cy = sum(y for _, y in points) // len(points)
        center_text(cx, cy - 10, label, body_font)

    def draw_system_structure() -> None:
        box(80, 160, 300, 285, "1 固定显示面")
        rotated_quad([(455, 135), (705, 170), (670, 315), (420, 280)], "2 姿态可调显示面")
        box(900, 160, 1120, 285, "3 地面/相邻显示面")
        box(95, 530, 315, 650, "4 入口交互终端")
        box(430, 520, 760, 670, "5 处理控制单元")
        box(880, 525, 1110, 650, "6 姿态驱动机构")
        box(455, 365, 735, 445, "7 姿态反馈单元")
        for start, end in [
            ((315, 590), (430, 595)),
            ((760, 595), (880, 595)),
            ((995, 525), (650, 315)),
            ((595, 365), (595, 315)),
            ((430, 560), (300, 255)),
            ((760, 555), (900, 255)),
        ]:
            arrow(start, end)
        center_text(600, 720, "结构连接关系：交互/检测 → 控制 → 驱动/反馈 → 多显示面同步输出", small_font)

    def draw_method_flow() -> None:
        steps = [
            ((70, 180, 260, 270), "S101 获取用户/视频输入"),
            ((340, 180, 530, 270), "S102 确定目标姿态"),
            ((610, 180, 800, 270), "S103 采集实际姿态"),
            ((880, 180, 1070, 270), "S104 建立边界投影"),
            ((210, 500, 430, 590), "S105 判定空白/遮挡"),
            ((500, 500, 720, 590), "S106 生成补偿/裁剪"),
            ((790, 500, 1010, 590), "S107 同步重映射输出"),
        ]
        for rect, label in steps:
            box(*rect, label, small_font)
        for start, end in [
            ((260, 225), (340, 225)),
            ((530, 225), (610, 225)),
            ((800, 225), (880, 225)),
            ((975, 270), (900, 500)),
            ((790, 545), (720, 545)),
            ((500, 545), (430, 545)),
        ]:
            arrow(start, end)
        draw.arc((300, 300, 900, 720), 20, 160, fill="black", width=2)
        arrow((310, 430), (260, 270), width=2)
        center_text(600, 355, "依据姿态反馈闭环更新映射参数", small_font)

    def draw_spatial_boundary() -> None:
        draw.line([(170, 640), (1030, 640)], fill="black", width=3)
        center_text(600, 660, "统一三维坐标系 X-Y 平面", small_font)
        box(170, 265, 375, 545, "固定显示面 A")
        rotated_quad([(520, 210), (770, 275), (720, 550), (470, 485)], "可调显示面 B")
        draw.line([(375, 310), (520, 275)], fill="black", width=2)
        draw.line([(375, 500), (470, 485)], fill="black", width=2)
        dashed_rect((380, 300, 510, 500), "空白区域 P1")
        dashed_rect((695, 290, 825, 520), "重叠/遮挡区域 P2")
        draw.ellipse((555, 70, 645, 160), outline="black", width=3)
        center_text(600, 165, "观看参考点 O", small_font)
        arrow((600, 160), (445, 340), width=2)
        arrow((600, 160), (745, 340), width=2)
        safe_text(830, 365, "边界投影线", small_font)
        draw.line([(780, 320), (950, 410)], fill="black", width=2)

    def draw_compensation_mapping() -> None:
        box(70, 170, 300, 300, "原始视频帧")
        box(455, 120, 745, 240, "补偿视口生成")
        box(455, 320, 745, 440, "遮挡掩膜/裁剪")
        box(900, 170, 1130, 300, "重映射输出帧")
        dashed_rect((110, 360, 280, 520), "待补偿空白块")
        dashed_rect((930, 360, 1100, 520), "同步输出区域")
        arrow((300, 235), (455, 180))
        arrow((300, 235), (455, 380))
        arrow((745, 180), (900, 235))
        arrow((745, 380), (900, 235))
        draw.line([(160, 220), (260, 220), (260, 270), (160, 270), (160, 220)], fill="black", width=2)
        draw.line([(960, 220), (1070, 220), (1070, 270), (960, 270), (960, 220)], fill="black", width=2)
        center_text(600, 590, "外转：生成补偿内容；内转：生成可见掩膜并删除/重分配被遮挡内容", small_font)

    center_text(600, 36, title or "专利附图", title_font)
    center_text(600, 78, (tech_description or "可调沉浸式显示系统")[:60], small_font)

    digits = "".join(ch for ch in str(figure_number or "") if ch.isdigit())
    if digits == "2":
        draw_method_flow()
    elif digits == "3":
        draw_spatial_boundary()
    elif digits == "4":
        draw_compensation_mapping()
    else:
        draw_system_structure()

    image.save(output_path, format="PNG")


def _write_fallback_svg(output_path: Path, title: str, tech_description: str) -> None:
    """Write a local line-art drawing so workflow artifacts still exist offline."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_title = html.escape(title or "专利附图")
    summary = html.escape((tech_description or "可调沉浸式显示系统")[:80])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820" viewBox="0 0 1200 820">
  <rect width="1200" height="820" fill="#fff"/>
  <text x="600" y="58" text-anchor="middle" font-family="Arial, sans-serif" font-size="30" font-weight="700">{safe_title}</text>
  <text x="600" y="94" text-anchor="middle" font-family="Arial, sans-serif" font-size="18">{summary}</text>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#111"/>
    </marker>
  </defs>
  <g fill="none" stroke="#111" stroke-width="3">
    <rect x="110" y="170" width="260" height="150" rx="4"/>
    <rect x="470" y="140" width="260" height="150" rx="4" transform="rotate(-10 600 215)"/>
    <rect x="830" y="170" width="260" height="150" rx="4"/>
    <rect x="430" y="560" width="340" height="120" rx="4"/>
    <rect x="120" y="520" width="230" height="120" rx="4"/>
    <rect x="850" y="520" width="230" height="120" rx="4"/>
    <path d="M370 245 C410 220, 430 215, 470 215" marker-end="url(#arrow)"/>
    <path d="M730 215 C770 215, 790 220, 830 245" marker-end="url(#arrow)"/>
    <path d="M240 320 L240 520" marker-end="url(#arrow)"/>
    <path d="M960 320 L960 520" marker-end="url(#arrow)"/>
    <path d="M350 580 L430 610" marker-end="url(#arrow)"/>
    <path d="M850 580 L770 610" marker-end="url(#arrow)"/>
  </g>
  <g font-family="Arial, sans-serif" font-size="22" fill="#111">
    <text x="240" y="250" text-anchor="middle">1 固定屏幕</text>
    <text x="600" y="215" text-anchor="middle">2 可调屏幕</text>
    <text x="960" y="250" text-anchor="middle">3 地面/相邻屏</text>
    <text x="235" y="585" text-anchor="middle">4 入口交互与身高检测</text>
    <text x="600" y="620" text-anchor="middle">5 姿态控制与映射模块</text>
    <text x="965" y="585" text-anchor="middle">6 画面补偿/过渡生成</text>
  </g>
  <g font-family="Arial, sans-serif" font-size="18" fill="#111">
    <text x="600" y="380" text-anchor="middle">根据用户输入、身高或视频内容生成目标屏幕姿态</text>
    <text x="600" y="420" text-anchor="middle">外转空白区域填补；内转遮挡/重叠区域裁剪、删除或重分配</text>
  </g>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")


class PatentDrawingGeneratorTool:
    """Generate patent drawing artifacts and return workflow-safe metadata."""

    name = "patent_drawing_generator"
    description = "根据技术方案生成专利附图，并返回可由工作流安全访问的附图元数据"

    def __init__(self, exports_root: Optional[Path] = None):
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        self._exports_root = exports_root or backend_dir / "exports"

    async def execute(
        self,
        tech_description: str,
        task_id: str,
        title: str = "专利附图",
        description: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        output_dir = self._exports_root / (task_id or "default") / "draft" / "drawings"
        output_dir.mkdir(parents=True, exist_ok=True)
        figure_number = str(kwargs.get("figure_number") or "图1")
        output_name = str(kwargs.get("output_name") or _safe_figure_filename(figure_number))
        if not output_name.lower().endswith(".png"):
            output_name = f"{Path(output_name).stem or 'fig1'}.png"
        output_path = output_dir / output_name
        fallback_path = output_dir / output_name

        image_config = _resolve_image_config(str(kwargs.get("profile_id") or "patent.writer.v1"))
        prompt = self._build_prompt(title, tech_description, figure_number, description)

        try:
            _generate_image_file(prompt, output_path, image_config)
        except Exception as exc:
            try:
                _write_fallback_png(fallback_path, title, tech_description, figure_number)
                mime_type = "image/png"
            except Exception:
                fallback_path = output_dir / f"{output_path.stem}.svg"
                _write_fallback_svg(fallback_path, title, tech_description)
                mime_type = "image/svg+xml"
            drawing_description = description or tech_description
            return make_tool_output(
                tool_name=self.name,
                data={
                    "drawings": [
                        {
                            "figure_number": figure_number,
                            "title": title,
                            "description": drawing_description,
                            "file_path": str(fallback_path),
                            "artifact_url": f"/api/v1/workflows/{task_id or 'default'}/artifacts/draft/drawings/{fallback_path.name}",
                            "mime_type": mime_type,
                            "fallback": True,
                            "prompt_version": "patent_drawing_v2",
                            "layout": _layout_key_for_figure(figure_number),
                            "warning": f"AI image generation unavailable: {exc}",
                        }
                    ]
                },
                success=True,
                start_time=start_time,
            )

        drawing_description = description or tech_description
        return make_tool_output(
            tool_name=self.name,
            data={
                "drawings": [
                    {
                        "figure_number": figure_number,
                        "title": title,
                        "description": drawing_description,
                        "file_path": str(output_path),
                        "artifact_url": f"/api/v1/workflows/{task_id or 'default'}/artifacts/draft/drawings/{output_path.name}",
                        "mime_type": "image/png",
                        "prompt_version": "patent_drawing_v2",
                        "layout": _layout_key_for_figure(figure_number),
                    }
                ]
            },
            success=True,
            start_time=start_time,
        )

    @staticmethod
    def _build_prompt(title: str, tech_description: str, figure_number: str, description: str = "") -> str:
        layout_requirements = {
            "图1": "画成系统结构框图：固定显示面、姿态可调显示面、地面/相邻显示面、入口交互终端、处理控制单元、姿态驱动机构、姿态反馈单元之间的连接关系。",
            "图2": "画成方法流程图：S101到S107的步骤框和顺序箭头，体现获取输入、确定姿态、采集反馈、边界投影、判定空白/遮挡、补偿裁剪、同步输出。",
            "图3": "画成空间几何示意图：固定显示面A、倾斜的可调显示面B、观看参考点O、边界投影线、空白区域P1、重叠/遮挡区域P2。",
            "图4": "画成画面处理映射示意图：原始视频帧、补偿视口生成、遮挡掩膜/裁剪、重映射输出帧、待补偿空白块和同步输出区域。",
        }
        normalized_figure = str(figure_number or "图1").replace(" ", "")
        return (
            "生成一张黑白线稿风格的中国专利说明书附图，避免照片质感和装饰性背景。"
            f"图号：{normalized_figure}。附图标题：{title}。"
            f"本图专属说明：{description or layout_requirements.get(normalized_figure, '')}。"
            f"必须采用的构图：{layout_requirements.get(normalized_figure, '画成与图1至图4不同的专利线稿构图。')}。"
            f"技术方案：{tech_description}。"
            "要求只表达本图主题，不要复用其他图的布局；使用模块框、流程箭头、几何边界、区域标号和编号标注。"
        )


def _layout_key_for_figure(figure_number: str) -> str:
    digits = "".join(ch for ch in str(figure_number or "") if ch.isdigit())
    return {
        "1": "system_structure",
        "2": "method_flow",
        "3": "spatial_boundary",
        "4": "compensation_mapping",
    }.get(digits or "1", f"figure_{digits or '1'}")
