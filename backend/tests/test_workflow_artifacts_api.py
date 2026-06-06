from __future__ import annotations


def test_workflow_artifact_endpoint_serves_generated_drawing(client, api_prefix, tmp_path, monkeypatch):
    from src.api import routes

    exports_root = tmp_path / "exports"
    drawing_path = exports_root / "drawing-task" / "draft" / "drawings" / "fig1.png"
    drawing_path.parent.mkdir(parents=True)
    drawing_path.write_bytes(b"fake-png")

    monkeypatch.setattr(routes, "_EXPORTS_ROOT", exports_root)

    response = client.get(f"{api_prefix}/workflows/drawing-task/artifacts/draft/drawings/fig1.png")

    assert response.status_code == 200
    assert response.content == b"fake-png"
    assert response.headers["content-type"] == "image/png"


def test_workflow_artifact_endpoint_blocks_path_traversal(client, api_prefix, tmp_path, monkeypatch):
    from src.api import routes

    exports_root = tmp_path / "exports"
    exports_root.mkdir()
    outside_file = tmp_path / "secret.png"
    outside_file.write_bytes(b"secret")

    monkeypatch.setattr(routes, "_EXPORTS_ROOT", exports_root)

    response = client.get(f"{api_prefix}/workflows/drawing-task/artifacts/../secret.png")

    assert response.status_code == 404
