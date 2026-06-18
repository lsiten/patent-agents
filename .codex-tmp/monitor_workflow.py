import json
import sys
import time
import urllib.request
from pathlib import Path


task_id = sys.argv[1]
base = Path("backend/exports") / task_id

for _ in range(240):
    try:
        with urllib.request.urlopen(f"http://localhost:8000/api/v1/workflows/{task_id}", timeout=5) as resp:
            data = json.load(resp)
    except Exception as exc:
        print("api_error", type(exc).__name__, exc, flush=True)
        data = {}

    state = data.get("current_state") or data.get("state")
    files = []
    if base.exists():
        for name in (
            "requirement/latest.json",
            "retrieval/latest.json",
            "draft/latest.json",
            "review/latest.json",
            "final/latest.json",
            "loop_state.json",
        ):
            path = base / name
            if path.exists():
                files.append(
                    f"{name}:{path.stat().st_size}:{time.strftime('%H:%M:%S', time.localtime(path.stat().st_mtime))}"
                )

    print(
        time.strftime("%H:%M:%S"),
        "state=",
        state,
        "updated=",
        data.get("updated_at"),
        "files=",
        " | ".join(files),
        flush=True,
    )
    if state in {"completed", "failed", "cancelled"}:
        break
    time.sleep(30)
