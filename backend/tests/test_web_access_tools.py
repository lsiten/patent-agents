from __future__ import annotations

import asyncio
from pathlib import Path

from src.agents.hermes.tools import web_access as web_access_tools
from src.agents.hermes.tools import web_access_common


def test_resolve_web_access_skill_dir_prefers_override(monkeypatch):
    monkeypatch.setenv("WEB_ACCESS_SKILL_DIR", "/tmp/custom-web-access")
    assert web_access_common.resolve_web_access_skill_dir() == Path("/tmp/custom-web-access")


def test_resolve_web_access_skill_dir_defaults_to_bundled_runtime(monkeypatch):
    monkeypatch.delenv("WEB_ACCESS_SKILL_DIR", raising=False)
    resolved = web_access_common.resolve_web_access_skill_dir()
    assert resolved.name == "web_access_runtime"
    assert resolved.parts[-4:] == ("src", "agents", "hermes", "web_access_runtime")


def test_parse_find_url_output_returns_structured_sections():
    stdout = """[书签] 1 条
  内部系统 | https://intranet.example.com | 工作 / 平台 | @Work

[历史] 1 条（按最近访问）
  控制台 | https://console.example.com | 2026-06-08 10:00:00 | visits=4 | @Work
"""

    parsed = web_access_common.parse_find_url_output(stdout)

    assert parsed["bookmarks"] == [
        {
            "name": "内部系统",
            "url": "https://intranet.example.com",
            "folder": "工作 / 平台",
            "profile": "Work",
        }
    ]
    assert parsed["history"] == [
        {
            "title": "控制台",
            "url": "https://console.example.com",
            "visit": "2026-06-08 10:00:00",
            "visit_count": 4,
            "profile": "Work",
        }
    ]


def test_web_access_find_url_tool_uses_script_output(monkeypatch):
    command_result = web_access_common.CommandResult(
        command=["node", "/tmp/find-url.mjs", "agent"],
        exit_code=0,
        stdout="[历史] 1 条（按最近访问）\n  Agent 平台 | https://agent.example.com | 2026-06-08 10:00:00\n",
        stderr="",
        script_path="/tmp/find-url.mjs",
    )

    monkeypatch.setattr(web_access_tools.WebAccessClient, "find_url", lambda self, **kwargs: command_result)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", lambda self: None)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "skill_dir", Path("/tmp/web-access"), raising=False)

    result = asyncio.run(web_access_tools.WebAccessFindUrlTool().execute(keywords="agent"))

    assert result["success"] is True
    assert result["data"]["result"]["history"][0]["url"] == "https://agent.example.com"
    assert result["data"]["command"]["script_path"] == "/tmp/find-url.mjs"


def test_web_access_find_url_tool_passes_browser_argument(monkeypatch):
    captured = {}

    def fake_find_url(self, **kwargs):
        captured.update(kwargs)
        return web_access_common.CommandResult(
            command=["node", "/tmp/find-url.mjs", "--browser", "chrome"],
            exit_code=0,
            stdout="[历史] 0 条（按最近访问）\n",
            stderr="",
            script_path="/tmp/find-url.mjs",
        )

    monkeypatch.setattr(web_access_tools.WebAccessClient, "find_url", fake_find_url)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", lambda self: None)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "skill_dir", Path("/tmp/web-access"), raising=False)

    result = asyncio.run(web_access_tools.WebAccessFindUrlTool().execute(keywords="agent", browser="chrome"))

    assert result["success"] is True
    assert captured["browser"] == "chrome"


def test_web_access_read_page_tool_runs_preflight_and_page_calls(monkeypatch):
    command_result = web_access_common.CommandResult(
        command=["node", "/tmp/check-deps.mjs"],
        exit_code=0,
        stdout="proxy: ready",
        stderr="",
        script_path="/tmp/check-deps.mjs",
    )
    responses = iter(
        [
            {"status_code": 200, "url": "http://127.0.0.1:3456/health", "content_type": "application/json", "body": {"status": "ok", "connected": True}},
            {"status_code": 200, "url": "http://127.0.0.1:3456/new", "content_type": "application/json", "body": {"targetId": "tab-1"}},
            {"status_code": 200, "url": "http://127.0.0.1:3456/info", "content_type": "application/json", "body": {"title": "Example", "url": "https://example.com"}},
            {"status_code": 200, "url": "http://127.0.0.1:3456/eval", "content_type": "application/json", "body": {"value": "Example"}},
            {"status_code": 200, "url": "http://127.0.0.1:3456/close", "content_type": "application/json", "body": {"success": True}},
        ]
    )

    def fake_init(self):
        self.skill_dir = Path("/tmp/web-access")
        self.proxy_base_url = "http://127.0.0.1:3456"

    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", fake_init)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "check_deps_with_browser", lambda self, browser="": command_result)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "proxy_request", lambda self, **kwargs: next(responses))

    result = asyncio.run(
        web_access_tools.WebAccessReadPageTool().execute(
            url="https://example.com",
            eval_expression="document.title",
            auto_close="true",
        )
    )

    assert result["success"] is True
    assert result["data"]["tab"]["target"] == "tab-1"
    assert result["data"]["evaluation"]["body"]["value"] == "Example"


def test_web_access_match_site_tool_returns_stdout(monkeypatch):
    command_result = web_access_common.CommandResult(
        command=["node", "/tmp/match-site.mjs", "xiaohongshu"],
        exit_code=0,
        stdout="--- 站点经验: xiaohongshu.com ---\n已知陷阱\n",
        stderr="",
        script_path="/tmp/match-site.mjs",
    )

    monkeypatch.setattr(web_access_tools.WebAccessClient, "match_site", lambda self, query: command_result)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", lambda self: None)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "skill_dir", Path("/tmp/web-access"), raising=False)

    result = asyncio.run(web_access_tools.WebAccessMatchSiteTool().execute(query="xiaohongshu"))

    assert result["success"] is True
    assert "站点经验" in result["data"]["matched_site_patterns"]


def test_web_access_browser_tool_builds_setfiles_request(monkeypatch):
    captured = {}

    def fake_init(self):
        self.skill_dir = Path("/tmp/web-access")
        self.proxy_base_url = "http://127.0.0.1:3456"

    def fake_proxy_request(self, **kwargs):
        captured.update(kwargs)
        return {
            "status_code": 200,
            "url": "http://127.0.0.1:3456/setFiles",
            "content_type": "application/json",
            "body": {"success": True, "files": 2},
        }

    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", fake_init)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "proxy_request", fake_proxy_request)

    result = asyncio.run(
        web_access_tools.WebAccessBrowserTool().execute(
            action="setFiles",
            target="tab-1",
            selector="input[type=file]",
            files_json='["/tmp/a.png", "/tmp/b.png"]',
        )
    )

    assert result["success"] is True
    assert captured["endpoint"] == "/setFiles"
    assert captured["body"] == {
        "selector": "input[type=file]",
        "files": ["/tmp/a.png", "/tmp/b.png"],
    }


def test_web_access_browser_tool_uses_post_body_for_new(monkeypatch):
    captured = {}

    def fake_init(self):
        self.skill_dir = Path("/tmp/web-access")
        self.proxy_base_url = "http://127.0.0.1:3456"

    def fake_proxy_request(self, **kwargs):
        captured.update(kwargs)
        return {
            "status_code": 200,
            "url": "http://127.0.0.1:3456/new",
            "content_type": "application/json",
            "body": {"targetId": "tab-2"},
        }

    monkeypatch.setattr(web_access_tools.WebAccessClient, "__init__", fake_init)
    monkeypatch.setattr(web_access_tools.WebAccessClient, "proxy_request", fake_proxy_request)

    result = asyncio.run(
        web_access_tools.WebAccessBrowserTool().execute(
            action="new",
            url="https://example.com",
        )
    )

    assert result["success"] is True
    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/new"
    assert captured["query"] == {}
    assert captured["body"] == "https://example.com"
