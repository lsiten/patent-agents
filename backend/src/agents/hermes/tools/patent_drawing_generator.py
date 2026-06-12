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


def _write_fallback_png(output_path: Path, title: str, tech_description: str) -> None:
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

    def center_text(x: int, y: int, text: str, font: Any) -> None:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            draw.text((x - (bbox[2] - bbox[0]) / 2, y), text, fill="black", font=font)
        except UnicodeEncodeError:
            fallback = "Patent Figure"
            bbox = draw.textbbox((0, 0), fallback, font=font)
            draw.text((x - (bbox[2] - bbox[0]) / 2, y), fallback, fill="black", font=font)

    center_text(600, 36, title or "专利附图", title_font)
    center_text(600, 78, (tech_description or "可调沉浸式显示系统")[:60], small_font)

    boxes = [
        ((110, 170, 370, 320), "1 固定屏幕"),
        ((470, 140, 730, 290), "2 可调屏幕"),
        ((830, 170, 1090, 320), "3 地面/相邻屏"),
        ((120, 520, 350, 640), "4 入口交互与身高检测"),
        ((430, 560, 770, 680), "5 姿态控制与映射模块"),
        ((850, 520, 1080, 640), "6 画面补偿/过渡生成"),
    ]
    for box, label in boxes:
        draw.rectangle(box, outline="black", width=3)
        center_text((box[0] + box[2]) // 2, (box[1] + box[3]) // 2 - 10, label, body_font)

    arrows = [
        ((370, 245), (470, 215)),
        ((730, 215), (830, 245)),
        ((240, 320), (240, 520)),
        ((960, 320), (960, 520)),
        ((350, 580), (430, 610)),
        ((850, 580), (770, 610)),
    ]
    for start, end in arrows:
        draw.line([start, end], fill="black", width=3)
        dx = 1 if end[0] >= start[0] else -1
        dy = 1 if end[1] >= start[1] else -1
        draw.polygon(
            [(end[0], end[1]), (end[0] - dx * 14, end[1] - dy * 6), (end[0] - dx * 6, end[1] - dy * 14)],
            fill="black",
        )

    center_text(600, 380, "根据用户输入、身高或视频内容生成目标屏幕姿态", small_font)
    center_text(600, 420, "外转空白区域填补；内转遮挡区域裁剪、删除或重分配", small_font)
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
        prompt = self._build_prompt(title, tech_description)

        try:
            _generate_image_file(prompt, output_path, image_config)
        except Exception as exc:
            try:
                _write_fallback_png(fallback_path, title, tech_description)
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
                    }
                ]
            },
            success=True,
            start_time=start_time,
        )

    @staticmethod
    def _build_prompt(title: str, tech_description: str) -> str:
        return (
            "生成一张黑白线稿风格的中国专利说明书附图，避免照片质感和装饰性背景。"
            f"附图标题：{title}。技术方案：{tech_description}。"
            "要求用模块框图、流程箭头和编号标注表达核心结构或步骤。"
        )
