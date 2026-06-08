"""Hermes tools that wrap the external web-access project."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from ..base import HermesTool, HermesToolDefinition, HermesToolParameter, make_tool_output
from .web_access_common import (
    WebAccessClient,
    ensure_screenshot_file_path,
    parse_find_url_output,
)


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class WebAccessReadPageTool(HermesTool):
    """Run web-access preflight and optionally open a page for lightweight inspection."""

    name = "web_access_read_page"
    description = "运行 web-access 前置检查，并可选打开页面返回基础信息与 DOM eval 结果"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "url": HermesToolParameter(
                    type="string",
                    description="可选。需要在后台新建 tab 打开的 URL",
                    required=False,
                ),
                "browser": HermesToolParameter(
                    type="string",
                    description="可选。一次性指定浏览器，如 chrome 或 edge，用于透传给 web-access check-deps --browser",
                    required=False,
                ),
                "eval_expression": HermesToolParameter(
                    type="string",
                    description="可选。打开页面后在 /eval 执行的 JS 表达式",
                    required=False,
                ),
                "auto_close": HermesToolParameter(
                    type="string",
                    description="可选。true 时在读取后关闭新建 tab，默认 true",
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        url: str = "",
        browser: str = "",
        eval_expression: str = "",
        auto_close: str = "true",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        client = WebAccessClient()

        try:
            preflight = client.check_deps_with_browser(browser=browser).to_dict()
            data: Dict[str, Any] = {
                "skill_dir": str(client.skill_dir),
                "proxy_base_url": client.proxy_base_url,
                "browser": browser or None,
                "preflight": preflight,
                "proxy_status": client.proxy_request(method="GET", endpoint="/health"),
            }

            if preflight["exit_code"] != 0:
                return make_tool_output(
                    tool_name=self.name,
                    data=data,
                    success=False,
                    error=preflight["stderr"] or preflight["stdout"] or "web-access preflight failed",
                    start_time=start_time,
                )

            if url:
                created = client.proxy_request(method="POST", endpoint="/new", body=url)
                target_id = ((created.get("body") or {}) if isinstance(created.get("body"), dict) else {}).get("targetId")
                data["tab"] = {"create": created, "target": target_id}
                if target_id:
                    data["page_info"] = client.proxy_request(
                        method="GET",
                        endpoint="/info",
                        query={"target": target_id},
                    )
                    if eval_expression:
                        data["evaluation"] = client.proxy_request(
                            method="POST",
                            endpoint="/eval",
                            query={"target": target_id},
                            body=eval_expression,
                        )
                    if _is_truthy(auto_close):
                        data["close"] = client.proxy_request(
                            method="GET",
                            endpoint="/close",
                            query={"target": target_id},
                        )

            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=True,
                start_time=start_time,
            )
        except Exception as exc:
            return make_tool_output(
                tool_name=self.name,
                data={"url": url, "browser": browser or None, "eval_expression": eval_expression},
                success=False,
                error=str(exc),
                start_time=start_time,
            )


class WebAccessFindUrlTool(HermesTool):
    """Query local Chrome bookmarks/history through find-url.mjs."""

    name = "web_access_find_url"
    description = "通过 web-access 的 find-url.mjs 查询本地 Chrome 书签与历史记录"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "keywords": HermesToolParameter(
                    type="string",
                    description="可选。空格分词，匹配 title + url",
                    required=False,
                ),
                "only": HermesToolParameter(
                    type="string",
                    description="可选。限定 bookmarks 或 history",
                    enum=["bookmarks", "history"],
                    required=False,
                ),
                "browser": HermesToolParameter(
                    type="string",
                    description="可选。限定浏览器 chrome 或 edge",
                    enum=["chrome", "edge"],
                    required=False,
                ),
                "limit": HermesToolParameter(
                    type="string",
                    description="可选。结果上限，默认 20，0 表示不限",
                    required=False,
                ),
                "since": HermesToolParameter(
                    type="string",
                    description="可选。历史时间窗，如 1d / 7h / YYYY-MM-DD",
                    required=False,
                ),
                "sort": HermesToolParameter(
                    type="string",
                    description="可选。history 排序 recent 或 visits，默认 recent",
                    enum=["recent", "visits"],
                    required=False,
                ),
            },
        )

    async def execute(
        self,
        keywords: str = "",
        only: str = "",
        browser: str = "",
        limit: str = "20",
        since: str = "",
        sort: str = "recent",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        client = WebAccessClient()

        try:
            command_result = client.find_url(
                keywords=keywords,
                only=only,
                browser=browser,
                limit=limit,
                since=since,
                sort=sort,
            )
            parsed = parse_find_url_output(command_result.stdout)
            data = {
                "skill_dir": str(client.skill_dir),
                "query": {
                    "keywords": keywords,
                    "only": only or None,
                    "browser": browser or None,
                    "limit": limit,
                    "since": since or None,
                    "sort": sort,
                },
                "result": parsed,
                "command": command_result.to_dict(),
            }
            success = command_result.exit_code == 0
            return make_tool_output(
                tool_name=self.name,
                data=data,
                success=success,
                error=None if success else (command_result.stderr or command_result.stdout or "find-url failed"),
                start_time=start_time,
            )
        except Exception as exc:
            return make_tool_output(
                tool_name=self.name,
                data={
                    "query": {
                        "keywords": keywords,
                        "only": only or None,
                        "browser": browser or None,
                        "limit": limit,
                        "since": since or None,
                        "sort": sort,
                    }
                },
                success=False,
                error=str(exc),
                start_time=start_time,
            )


class WebAccessBrowserTool(HermesTool):
    """Thin wrapper over the web-access CDP proxy HTTP API."""

    name = "web_access_browser"
    description = "通过 web-access CDP Proxy 执行 tab 管理、导航、DOM eval、交互、截图与健康检查"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "action": HermesToolParameter(
                    type="string",
                    description="代理操作：health/targets/new/navigate/back/info/eval/click/clickAt/setFiles/scroll/screenshot/close/preflight",
                    enum=[
                        "health",
                        "targets",
                        "new",
                        "navigate",
                        "back",
                        "info",
                        "eval",
                        "click",
                        "clickAt",
                        "setFiles",
                        "scroll",
                        "screenshot",
                        "close",
                        "preflight",
                    ],
                    required=True,
                ),
                "target": HermesToolParameter(type="string", description="目标 tab 的 targetId", required=False),
                "url": HermesToolParameter(type="string", description="new / navigate 使用的 URL", required=False),
                "browser": HermesToolParameter(type="string", description="可选。preflight 时一次性指定浏览器，如 chrome 或 edge", required=False),
                "expression": HermesToolParameter(type="string", description="eval 使用的 JS 表达式", required=False),
                "selector": HermesToolParameter(type="string", description="click / clickAt / setFiles 使用的 CSS selector", required=False),
                "files_json": HermesToolParameter(type="string", description="setFiles 用 JSON 字符串，例如 [\"/tmp/a.png\"]", required=False),
                "file_path": HermesToolParameter(type="string", description="screenshot 输出路径；缺省时自动生成临时文件", required=False),
                "y": HermesToolParameter(type="string", description="scroll 垂直像素值", required=False),
                "direction": HermesToolParameter(type="string", description="scroll 方向：down/up/top/bottom", required=False),
                "format": HermesToolParameter(type="string", description="screenshot 格式：png/jpeg", enum=["png", "jpeg"], required=False),
            },
        )

    async def execute(
        self,
        action: str,
        target: str = "",
        url: str = "",
        browser: str = "",
        expression: str = "",
        selector: str = "",
        files_json: str = "",
        file_path: str = "",
        y: str = "",
        direction: str = "",
        format: str = "png",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        client = WebAccessClient()

        try:
            if action == "preflight":
                result = client.check_deps_with_browser(browser=browser).to_dict()
                success = result["exit_code"] == 0
                return make_tool_output(
                    tool_name=self.name,
                    data={
                        "action": action,
                        "skill_dir": str(client.skill_dir),
                        "browser": browser or None,
                        "result": result,
                    },
                    success=success,
                    error=None if success else (result["stderr"] or result["stdout"] or "web-access preflight failed"),
                    start_time=start_time,
                )

            method, endpoint, query, body = self._build_proxy_request(
                action=action,
                target=target,
                url=url,
                expression=expression,
                selector=selector,
                files_json=files_json,
                file_path=file_path,
                y=y,
                direction=direction,
                format=format,
            )
            response = client.proxy_request(
                method=method,
                endpoint=endpoint,
                query=query,
                body=body,
            )
            body_payload = response.get("body")
            error_message = None
            success = int(response.get("status_code", 500)) < 400
            if isinstance(body_payload, dict) and body_payload.get("error"):
                success = False
                error_message = str(body_payload["error"])

            return make_tool_output(
                tool_name=self.name,
                data={
                    "action": action,
                    "proxy_base_url": client.proxy_base_url,
                    "request": {
                        "method": method,
                        "endpoint": endpoint,
                        "query": query,
                        "body": body if not isinstance(body, (dict, list)) else json.dumps(body, ensure_ascii=False),
                    },
                    "response": response,
                },
                success=success,
                error=error_message,
                start_time=start_time,
            )
        except Exception as exc:
            return make_tool_output(
                tool_name=self.name,
                data={"action": action, "target": target, "url": url, "browser": browser or None},
                success=False,
                error=str(exc),
                start_time=start_time,
            )

    @staticmethod
    def _build_proxy_request(
        *,
        action: str,
        target: str,
        url: str,
        expression: str,
        selector: str,
        files_json: str,
        file_path: str,
        y: str,
        direction: str,
        format: str,
    ) -> tuple[str, str, Dict[str, Any], Any]:
        if action == "health":
            return "GET", "/health", {}, None
        if action == "targets":
            return "GET", "/targets", {}, None
        if action == "new":
            return "POST", "/new", {}, url or "about:blank"
        if action == "navigate":
            return (
                "POST",
                "/navigate",
                {"target": WebAccessBrowserTool._require(target, "target")},
                WebAccessBrowserTool._require(url, "url"),
            )
        if action == "back":
            return "GET", "/back", {"target": WebAccessBrowserTool._require(target, "target")}, None
        if action == "info":
            return "GET", "/info", {"target": WebAccessBrowserTool._require(target, "target")}, None
        if action == "eval":
            return "POST", "/eval", {"target": WebAccessBrowserTool._require(target, "target")}, WebAccessBrowserTool._require(expression, "expression")
        if action == "click":
            return "POST", "/click", {"target": WebAccessBrowserTool._require(target, "target")}, WebAccessBrowserTool._require(selector, "selector")
        if action == "clickAt":
            return "POST", "/clickAt", {"target": WebAccessBrowserTool._require(target, "target")}, WebAccessBrowserTool._require(selector, "selector")
        if action == "setFiles":
            files = json.loads(WebAccessBrowserTool._require(files_json, "files_json"))
            if not isinstance(files, list):
                raise ValueError("files_json must decode to a JSON array")
            return (
                "POST",
                "/setFiles",
                {"target": WebAccessBrowserTool._require(target, "target")},
                {"selector": WebAccessBrowserTool._require(selector, "selector"), "files": files},
            )
        if action == "scroll":
            query = {"target": WebAccessBrowserTool._require(target, "target")}
            if y:
                query["y"] = y
            if direction:
                query["direction"] = direction
            return "GET", "/scroll", query, None
        if action == "screenshot":
            output_path = ensure_screenshot_file_path(file_path=file_path, image_format=format or "png")
            return "GET", "/screenshot", {"target": WebAccessBrowserTool._require(target, "target"), "file": output_path, "format": format or "png"}, None
        if action == "close":
            return "GET", "/close", {"target": WebAccessBrowserTool._require(target, "target")}, None
        raise ValueError(f"unsupported action: {action}")

    @staticmethod
    def _require(value: str, field_name: str) -> str:
        if not value:
            raise ValueError(f"{field_name} is required for this action")
        return value


class WebAccessMatchSiteTool(HermesTool):
    """Match site-pattern knowledge for a user query."""

    name = "web_access_match_site"
    description = "根据查询内容匹配 bundled web-access 的站点经验文件"

    def _build_definition(self) -> HermesToolDefinition:
        return HermesToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "query": HermesToolParameter(
                    type="string",
                    description="需要匹配站点经验的查询文本",
                    required=True,
                ),
            },
        )

    async def execute(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        start_time = datetime.now()
        client = WebAccessClient()

        try:
            command_result = client.match_site(query=query)
            success = command_result.exit_code == 0
            return make_tool_output(
                tool_name=self.name,
                data={
                    "skill_dir": str(client.skill_dir),
                    "query": query,
                    "matched_site_patterns": command_result.stdout.strip(),
                    "command": command_result.to_dict(),
                },
                success=success,
                error=None if success else (command_result.stderr or command_result.stdout or "match-site failed"),
                start_time=start_time,
            )
        except Exception as exc:
            return make_tool_output(
                tool_name=self.name,
                data={"query": query},
                success=False,
                error=str(exc),
                start_time=start_time,
            )
