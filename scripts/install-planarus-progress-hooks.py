"""Install the opt-in Planarus Stop hook for local Codex and Claude Code.

Existing user settings and hook groups are preserved. The hook activates only
inside repositories with a .planarus-progress.json project link.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

MESSAGE = "Checking Planarus progress"
HOOK_SCRIPT = Path(__file__).with_name("planarus-progress-hook.py").resolve()


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def add_hook(data: dict, handler: dict) -> bool:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    groups = hooks.setdefault("Stop", [])
    if not isinstance(groups, list):
        raise ValueError("hooks.Stop must be an array")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        for i, old in enumerate(group["hooks"]):
            if isinstance(old, dict) and old.get("statusMessage") == MESSAGE:
                if old == handler:
                    return False
                group["hooks"][i] = handler
                return True
    groups.append({"hooks": [handler]})
    return True


def write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".planarus-hooks-", delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        if path.exists():
            os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(home: Path, dry_run: bool = False) -> list[tuple[Path, bool]]:
    if not HOOK_SCRIPT.is_file():
        raise FileNotFoundError(HOOK_SCRIPT)
    command = [sys.executable, str(HOOK_SCRIPT)]
    codex_handler = {
        "type": "command",
        "command": shlex.join(command),
        "commandWindows": subprocess.list2cmdline(command),
        "timeout": 10,
        "statusMessage": MESSAGE,
    }
    claude_handler = {
        "type": "command",
        "command": sys.executable,
        "args": [str(HOOK_SCRIPT)],
        "timeout": 10,
        "statusMessage": MESSAGE,
    }
    targets = [
        (home / ".codex" / "hooks.json", codex_handler),
        (home / ".claude" / "settings.json", claude_handler),
    ]
    prepared = []
    for path, handler in targets:
        data = read_settings(path)
        changed = add_hook(data, handler)
        prepared.append((path, data, changed))
    if not dry_run:
        for path, data, changed in prepared:
            if changed:
                write_settings(path, data)
    return [(path, changed) for path, _, changed in prepared]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for path, changed in install(args.home, args.dry_run):
        print(f"{'Would update' if args.dry_run and changed else 'Updated' if changed else 'Already set'}: {path}")


if __name__ == "__main__":
    main()
