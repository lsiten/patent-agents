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
    """Resolve image config through agent YAML/runtime overrides and LLM fallback."""
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

    return settings.image_gen.resolve_with_llm_fallback(settings.llm, image_overrides)


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
        output_path = output_dir / "fig1.png"

        image_config = _resolve_image_config(str(kwargs.get("profile_id") or "patent.writer.v1"))
        prompt = self._build_prompt(title, tech_description)

        try:
            _generate_image_file(prompt, output_path, image_config)
        except Exception as exc:
            return make_tool_output(
                tool_name=self.name,
                data={"drawings": []},
                success=False,
                error=str(exc),
                start_time=start_time,
            )

        drawing_description = description or tech_description
        return make_tool_output(
            tool_name=self.name,
            data={
                "drawings": [
                    {
                        "figure_number": "图1",
                        "title": title,
                        "description": drawing_description,
                        "file_path": str(output_path),
                        "artifact_url": f"/api/v1/workflows/{task_id or 'default'}/artifacts/draft/drawings/fig1.png",
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
