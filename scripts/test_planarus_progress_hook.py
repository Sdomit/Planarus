"""Focused contract checks for the shared Codex/Claude Stop hook."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("planarus-progress-hook.py")
spec = importlib.util.spec_from_file_location("planarus_progress_hook", SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
installer_spec = importlib.util.spec_from_file_location("planarus_progress_installer", SCRIPT.with_name("install-planarus-progress-hooks.py"))
installer = importlib.util.module_from_spec(installer_spec)
installer_spec.loader.exec_module(installer)


class ProgressHookTest(unittest.TestCase):
    def test_first_stop_requests_mcp_sync_only_for_linked_project(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parent) as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            nested = repo / "src"
            nested.mkdir()
            (repo / hook.MARKER).write_text(json.dumps({
                "project_id": "proj_123abc", "project_title": "Example"
            }), encoding="utf-8")
            event = {"hook_event_name": "Stop", "cwd": str(nested), "stop_hook_active": False}
            result = hook.response(event)
            self.assertEqual(result["decision"], "block")
            self.assertIn("proj_123abc", result["reason"])
            self.assertIn("each approval ID", result["reason"])
            self.assertEqual(hook.response({**event, "stop_hook_active": True}), {"continue": True})
            self.assertEqual(hook.response({**event, "last_assistant_message": "Planarus sync: no update needed: read only"}), {"continue": True})

    def test_unlinked_repo_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parent) as tmp:
            (Path(tmp) / ".git").mkdir()
            self.assertEqual(hook.response({"hook_event_name": "Stop", "cwd": tmp}), {"continue": True})

    def test_command_prints_json_for_both_clients(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parent) as tmp:
            event = {"hook_event_name": "Stop", "cwd": tmp}
            proc = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(event), text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(proc.stdout), {"continue": True})
            self.assertEqual(proc.stderr, "")

    def test_installer_preserves_existing_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parent) as tmp:
            home = Path(tmp)
            claude = home / ".claude" / "settings.json"
            claude.parent.mkdir()
            claude.write_text(json.dumps({"theme": "dark", "hooks": {"PreCompact": [{"hooks": [{"type": "command", "command": "existing"}]}]}}), encoding="utf-8")
            installer.install(home)
            first = json.loads(claude.read_text(encoding="utf-8"))
            self.assertEqual(first["theme"], "dark")
            self.assertEqual(first["hooks"]["PreCompact"][0]["hooks"][0]["command"], "existing")
            self.assertEqual(first["hooks"]["Stop"][0]["hooks"][0]["statusMessage"], installer.MESSAGE)
            self.assertEqual(installer.install(home), [
                (home / ".codex" / "hooks.json", False),
                (home / ".claude" / "settings.json", False),
            ])


if __name__ == "__main__":
    unittest.main()
