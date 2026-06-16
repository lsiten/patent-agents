"""Patent drawing generation tool using project image/LLM configuration."""

from __future__ import annotations

import base64
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.agents.hermes.base import make_tool_output
from src.core.config import settings
from src.core.logging import get_logger


logger = get_logger(__name__)


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
        title: str = "",
        description: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        figure_number = str(kwargs.get("figure_number") or "图1")
        drawing_title = str(title or "").strip()
        drawing_description = str(description or "").strip()
        if not drawing_title:
            return make_tool_output(
                tool_name=self.name,
                data={
                    "drawings": [],
                    "figure_number": figure_number,
                    "prompt_version": "patent_drawing_v3",
                    "layout": _layout_key_for_figure(figure_number),
                },
                success=False,
                error=(
                    "title is required. The drawing tool does not provide generic figure titles."
                ),
                start_time=start_time,
            )
        if len(drawing_description) < 20:
            return make_tool_output(
                tool_name=self.name,
                data={
                    "drawings": [],
                    "figure_number": figure_number,
                    "title": drawing_title,
                    "prompt_version": "patent_drawing_v3",
                    "layout": _layout_key_for_figure(figure_number),
                },
                success=False,
                error=(
                    "description must contain the concrete drawing content for this figure. "
                    "The drawing tool does not provide built-in patent content templates."
                ),
                start_time=start_time,
            )
        output_dir = self._exports_root / (task_id or "default") / "draft" / "drawings"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_name = str(kwargs.get("output_name") or _safe_figure_filename(figure_number))
        if not output_name.lower().endswith(".png"):
            output_name = f"{Path(output_name).stem or 'fig1'}.png"
        output_path = output_dir / output_name
        image_config = _resolve_image_config(str(kwargs.get("profile_id") or "patent.writer.v1"))
        prompt = self._build_prompt(drawing_title, tech_description, figure_number, drawing_description)

        try:
            _generate_image_file(prompt, output_path, image_config)
        except Exception as exc:
            logger.error("Patent drawing generation failed", error=str(exc), figure_number=figure_number)
            return make_tool_output(
                tool_name=self.name,
                data={
                    "drawings": [],
                    "figure_number": figure_number,
                    "title": drawing_title,
                    "prompt_version": "patent_drawing_v3",
                    "layout": _layout_key_for_figure(figure_number),
                    "image_config_source": image_config.get("source"),
                },
                success=False,
                error=f"AI image generation failed; no drawing artifact was created: {exc}",
                start_time=start_time,
            )

        return make_tool_output(
            tool_name=self.name,
            data={
                "drawings": [
                    {
                        "figure_number": figure_number,
                        "title": drawing_title,
                        "description": drawing_description,
                        "file_path": str(output_path),
                        "artifact_url": f"/api/v1/workflows/{task_id or 'default'}/artifacts/draft/drawings/{output_path.name}",
                        "mime_type": "image/png",
                        "prompt_version": "patent_drawing_v3",
                        "layout": _layout_key_for_figure(figure_number),
                    }
                ]
            },
            success=True,
            start_time=start_time,
        )

    @staticmethod
    def _build_prompt(title: str, tech_description: str, figure_number: str, description: str = "") -> str:
        normalized_figure = str(figure_number or "图1").replace(" ", "")
        return (
            "生成一张黑白线稿风格的中国专利说明书附图，避免照片质感和装饰性背景。"
            f"图号：{normalized_figure}。附图标题：{title}。"
            f"本图必须表达的具体内容：{description}。"
            f"专利整体技术方案背景：{tech_description}。"
            "只能依据“本图必须表达的具体内容”决定图中模块、步骤、结构、连接线、箭头和编号。"
            "不得套用内置领域模板，不得复用其他图的布局，不得只替换标题。"
            "如果适合用框图、流程图、结构示意图或关系图，请根据本图具体内容自行选择最清楚的专利线稿表达。"
        )


def _layout_key_for_figure(figure_number: str) -> str:
    digits = "".join(ch for ch in str(figure_number or "") if ch.isdigit())
    return f"figure_{digits or '1'}"
