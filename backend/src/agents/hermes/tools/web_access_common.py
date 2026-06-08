"""Shared helpers for Hermes web-access tool wrappers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BUNDLED_WEB_ACCESS_RUNTIME_DIR = (
    Path(__file__).resolve().parent.parent / "web_access_runtime"
)
DEFAULT_PROXY_PORT = 3456


def resolve_web_access_skill_dir() -> Path:
    """Resolve the bundled web-access runtime directory.

    Priority:
    1. WEB_ACCESS_SKILL_DIR override
    2. bundled runtime inside this repository
    """
    override = os.environ.get("WEB_ACCESS_SKILL_DIR")
    if override:
        return Path(override).expanduser()
    return BUNDLED_WEB_ACCESS_RUNTIME_DIR


def resolve_proxy_base_url() -> str:
    """Resolve the local CDP proxy base URL."""
    override = os.environ.get("WEB_ACCESS_PROXY_BASE_URL")
    if override:
        return override.rstrip("/")
    port = int(os.environ.get("CDP_PROXY_PORT", str(DEFAULT_PROXY_PORT)))
    return f"http://127.0.0.1:{port}"


@dataclass
class CommandResult:
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str
    script_path: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "script_path": self.script_path,
        }


class WebAccessClient:
    """Thin subprocess + HTTP wrapper around the external web-access project."""

    def __init__(
        self,
        skill_dir: Optional[Path] = None,
        proxy_base_url: Optional[str] = None,
    ):
        self.skill_dir = Path(skill_dir or resolve_web_access_skill_dir()).expanduser()
        self.proxy_base_url = (proxy_base_url or resolve_proxy_base_url()).rstrip("/")

    def script_path(self, script_name: str) -> Path:
        return self.skill_dir / "scripts" / script_name

    def run_node_script(
        self,
        script_name: str,
        args: Optional[List[str]] = None,
        timeout: int = 60,
    ) -> CommandResult:
        script_path = self.script_path(script_name)
        if not script_path.is_file():
            raise FileNotFoundError(f"web-access script not found: {script_path}")

        command = ["node", str(script_path), *(args or [])]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            script_path=str(script_path),
        )

    def check_deps(self, timeout: int = 90) -> CommandResult:
        return self.check_deps_with_browser(browser="", timeout=timeout)

    def check_deps_with_browser(self, browser: str = "", timeout: int = 90) -> CommandResult:
        args: List[str] = []
        if browser:
            args.extend(["--browser", browser])
        return self.run_node_script("check-deps.mjs", args=args, timeout=timeout)

    def find_url(
        self,
        *,
        keywords: str = "",
        only: str = "",
        browser: str = "",
        limit: str = "20",
        since: str = "",
        sort: str = "recent",
        timeout: int = 90,
    ) -> CommandResult:
        args: List[str] = []
        if keywords:
            args.extend(part for part in keywords.split() if part)
        if only:
            args.extend(["--only", only])
        if browser:
            args.extend(["--browser", browser])
        if limit:
            args.extend(["--limit", str(limit)])
        if since:
            args.extend(["--since", since])
        if sort:
            args.extend(["--sort", sort])
        return self.run_node_script("find-url.mjs", args=args, timeout=timeout)

    def match_site(self, query: str, timeout: int = 30) -> CommandResult:
        args = [query] if query else []
        return self.run_node_script("match-site.mjs", args=args, timeout=timeout)

    def proxy_request(
        self,
        *,
        method: str,
        endpoint: str,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Any] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        query_items = {
            key: value
            for key, value in (query or {}).items()
            if value is not None and value != ""
        }
        url = f"{self.proxy_base_url}{endpoint}"
        if query_items:
            url = f"{url}?{urlencode(query_items, doseq=True)}"

        data: Optional[bytes] = None
        headers: Dict[str, str] = {}
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            elif isinstance(body, bytes):
                data = body
            else:
                data = str(body).encode("utf-8")
                headers["Content-Type"] = "text/plain; charset=utf-8"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
                return {
                    "status_code": getattr(response, "status", response.getcode()),
                    "url": url,
                    "content_type": content_type,
                    "body": self._decode_response_body(raw, content_type),
                }
        except HTTPError as exc:
            raw = exc.read()
            content_type = exc.headers.get("Content-Type", "")
            return {
                "status_code": exc.code,
                "url": url,
                "content_type": content_type,
                "body": self._decode_response_body(raw, content_type),
            }
        except URLError as exc:
            raise RuntimeError(f"web-access proxy request failed: {exc.reason}") from exc

    @staticmethod
    def _decode_response_body(raw: bytes, content_type: str) -> Any:
        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace")
        if "application/json" in content_type:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


def parse_find_url_output(stdout: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse find-url.mjs stdout into structured bookmark/history entries."""
    parsed: Dict[str, List[Dict[str, Any]]] = {"bookmarks": [], "history": []}
    current_section: Optional[str] = None

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if line.startswith("[书签]"):
            current_section = "bookmarks"
            continue
        if line.startswith("[历史]"):
            current_section = "history"
            continue
        if not line.strip() or current_section is None:
            continue

        parts = [part.strip() for part in line.strip().split(" | ")]
        profile = None
        visits = None
        if parts and parts[-1].startswith("@"):
            profile = parts.pop()[1:]
        if current_section == "bookmarks":
            item: Dict[str, Any] = {
                "name": parts[0] if len(parts) > 0 else "",
                "url": parts[1] if len(parts) > 1 else "",
                "folder": parts[2] if len(parts) > 2 else "",
            }
            if profile:
                item["profile"] = profile
            parsed[current_section].append(item)
            continue

        filtered_parts: List[str] = []
        for part in parts:
            if part.startswith("visits="):
                try:
                    visits = int(part.split("=", 1)[1])
                except ValueError:
                    visits = None
            else:
                filtered_parts.append(part)

        item = {
            "title": filtered_parts[0] if len(filtered_parts) > 0 else "",
            "url": filtered_parts[1] if len(filtered_parts) > 1 else "",
            "visit": filtered_parts[2] if len(filtered_parts) > 2 else "",
        }
        if visits is not None:
            item["visit_count"] = visits
        if profile:
            item["profile"] = profile
        parsed[current_section].append(item)

    return parsed


def ensure_screenshot_file_path(file_path: str = "", image_format: str = "png") -> str:
    """Ensure screenshot requests always use a file output path."""
    if file_path:
        return file_path
    suffix = ".jpeg" if image_format == "jpeg" else ".png"
    fd, tmp_path = tempfile.mkstemp(prefix="web-access-shot-", suffix=suffix)
    os.close(fd)
    return tmp_path
