"""Codex/Claude Stop hook: ask for one MCP progress check for a linked repo.

Reads only the hook JSON on stdin and a small .planarus-progress.json marker in
the current repository. It does not write project data or call the network.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARKER = ".planarus-progress.json"
SYNC_LINE = re.compile(r"(?im)^Planarus sync:\s*\S")
PROJECT_ID = re.compile(r"^proj_[A-Za-z0-9]+$")


def linked_project(cwd: str) -> tuple[str, str] | None:
    path = Path(cwd).resolve()
    for directory in (path, *path.parents):
        marker = directory / MARKER
        if marker.is_file():
            if marker.stat().st_size > 4096:
                raise ValueError("project link is too large")
            data = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not PROJECT_ID.fullmatch(str(data.get("project_id", ""))):
                raise ValueError("project link has no valid project_id")
            title = str(data.get("project_title", "")).strip()[:120]
            title = " ".join(title.split())
            return data["project_id"], title
        if (directory / ".git").exists():
            break
    return None


def response(event: dict) -> dict:
    if event.get("hook_event_name") != "Stop" or event.get("stop_hook_active"):
        return {"continue": True}
    if SYNC_LINE.search(str(event.get("last_assistant_message") or "")):
        return {"continue": True}
    try:
        project = linked_project(str(event.get("cwd") or ""))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"continue": True, "systemMessage": "Planarus progress hook: fix .planarus-progress.json in this repository."}
    if project is None:
        return {"continue": True}
    project_id, title = project
    name = f"{title} ({project_id})" if title else project_id
    return {
        "decision": "block",
        "reason": (
            f"Before finishing, sync progress for the linked Planarus project {name}. "
            "Use the connected Planarus MCP: read the relevant current records, "
            "then propose meaningful changes with the matching tool for phases, "
            "tasks, milestones, decisions, risks, comments, URL links, or typed connections. "
            "Make Approval Queue entries easy to scan: specific short titles, "
            "a plain first summary sentence, concise Markdown paragraphs or "
            "bullets for details and completion criteria, and content in the right "
            "fields (decision and rationale; risk and mitigation). "
            "Do not stack pending updates to the same record; wait for the earlier "
            "approval to be applied, then re-read the record before proposing more. "
            "Omit status on create for the default; before setting one, call "
            "list_status_options for that project's task or decision keys. "
            "Give the user each approval ID; if Auto accept is enabled, poll "
            "get_approval_status before claiming a record was applied. "
            "If this turn made no plan-relevant change, no proposal is needed. "
            "End your response with one line: 'Planarus sync: <approval ID>', "
            "'Planarus sync: no update needed: <reason>', or "
            "'Planarus sync: unavailable: <reason>'."
        ),
    }


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        event = json.load(sys.stdin)
        result = response(event if isinstance(event, dict) else {})
    except (ValueError, OSError, json.JSONDecodeError):
        result = {"continue": True}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
