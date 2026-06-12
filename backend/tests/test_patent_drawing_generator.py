from __future__ import annotations


import pytest


@pytest.mark.asyncio
async def test_patent_drawing_generator_uses_system_image_config(monkeypatch, tmp_path):
    from src.agents.hermes.tools import patent_drawing_generator as drawing_module
    from src.agents.hermes.tools.patent_drawing_generator import PatentDrawingGeneratorTool

    captured = {}

    def fake_generate_image(prompt, output_path, image_config):
        captured["prompt"] = prompt
        captured["output_path"] = output_path
        captured["image_config"] = image_config
        output_path.write_bytes(b"fake-png")

    monkeypatch.setattr(drawing_module, "_generate_image_file", fake_generate_image)
    monkeypatch.setattr(
        drawing_module,
        "_resolve_image_config",
        lambda profile_id="patent.writer.v1": {
            "provider": "azure_aoai",
            "base_url": "https://configured-image.example/v1",
            "api_key": "configured-image-key",
            "model_id": "configured-image-model",
        },
    )

    tool = PatentDrawingGeneratorTool(exports_root=tmp_path)
    result = await tool.execute(
        task_id="drawing-task",
        tech_description="一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
        title="Cave折幕空间视频补偿系统结构示意图",
    )

    assert result["success"] is True
    assert captured["image_config"] == {
        "provider": "azure_aoai",
        "base_url": "https://configured-image.example/v1",
        "api_key": "configured-image-key",
        "model_id": "configured-image-model",
    }
    assert result["data"]["drawings"] == [
        {
            "figure_number": "图1",
            "title": "Cave折幕空间视频补偿系统结构示意图",
            "description": "一种入口预配置Cave折幕姿态并连续处理跨屏画面的方法。",
            "file_path": str(tmp_path / "drawing-task" / "draft" / "drawings" / "fig1.png"),
            "artifact_url": "/api/v1/workflows/drawing-task/artifacts/draft/drawings/fig1.png",
            "mime_type": "image/png",
        }
    ]


@pytest.mark.asyncio
async def test_patent_drawing_generator_uses_resolved_image_config(monkeypatch, tmp_path):
    from src.agents.hermes.tools import patent_drawing_generator as drawing_module
    from src.agents.hermes.tools.patent_drawing_generator import PatentDrawingGeneratorTool

    captured = {}

    def fake_generate_image(prompt, output_path, image_config):
        captured["image_config"] = image_config
        output_path.write_bytes(b"fake-png")

    monkeypatch.setattr(drawing_module, "_generate_image_file", fake_generate_image)
    monkeypatch.setattr(
        drawing_module,
        "_resolve_image_config",
        lambda profile_id="patent.writer.v1": {
            "provider": "openai",
            "base_url": "https://llm-proxy.example/v1",
            "api_key": "llm-configured-key",
            "model_id": "gpt-image-2",
        },
    )

    tool = PatentDrawingGeneratorTool(exports_root=tmp_path)
    result = await tool.execute(
        task_id="llm-fallback-task",
        tech_description="一种基于传感器检测身高并调整屏幕姿态的系统。",
    )

    assert result["success"] is True
    assert captured["image_config"]["api_key"] == "llm-configured-key"
    assert captured["image_config"]["model_id"] == "gpt-image-2"


def test_resolve_image_config_passes_agent_overrides(monkeypatch):
    from src.agents.hermes.tools import patent_drawing_generator as drawing_module

    captured = {}

    class FakeAgentConfig:
        image_gen = {
            "provider": "openai",
            "base_url": "https://agent-image.example/v1",
            "api_key": "agent-image-key",
            "model_id": "agent-image-model",
        }

    monkeypatch.setattr(
        "src.agents.agent_config.get_agent_config",
        lambda profile_id: FakeAgentConfig(),
    )
    monkeypatch.setattr(
        "src.core.override_store.get_override_store",
        lambda: type("Store", (), {"get_image_gen_override": lambda self, profile_id: {}})(),
    )

    def fake_resolve_for_agent(self, overrides):
        captured["overrides"] = overrides
        return {"provider": overrides["provider"], "api_key": overrides["api_key"]}

    monkeypatch.setattr(type(drawing_module.settings.image_gen), "resolve_for_agent", fake_resolve_for_agent)

    resolved = drawing_module._resolve_image_config("patent.writer.v1")

    assert captured["overrides"] == FakeAgentConfig.image_gen
    assert resolved == {"provider": "openai", "api_key": "agent-image-key"}
