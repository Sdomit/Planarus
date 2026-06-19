from app.fsmemory.provisioner import provision_tree
from app.fsmemory.spec import RESERVED_DIRS
from app.models.project import Project
from app.models.workspace import Workspace

_TS = "2026-06-19T00:00:00+00:00"


def _proj_ws(root):
    ws = Workspace(id="ws_1", name="WS", slug="ws", created_at=_TS, updated_at=_TS)
    proj = Project(
        id="proj_1",
        workspace_id="ws_1",
        title="P",
        slug="p",
        folder_path=str(root),
        created_at=_TS,
        updated_at=_TS,
    )
    return proj, ws


def test_provision_creates_full_tree(tmp_path):
    proj, ws = _proj_ws(tmp_path)
    provision_tree(str(tmp_path), proj, ws)

    assert (tmp_path / ".agentboard").is_dir()
    assert (tmp_path / "context").is_dir()
    for rel_dir in RESERVED_DIRS:
        assert (tmp_path / rel_dir).is_dir(), rel_dir

    for name in ("project.json", "workspace-link.json", "settings.json", "audit-log.jsonl"):
        assert (tmp_path / ".agentboard" / name).is_file(), name


def test_provision_is_idempotent(tmp_path):
    proj, ws = _proj_ws(tmp_path)
    provision_tree(str(tmp_path), proj, ws)
    pj = tmp_path / ".agentboard" / "project.json"
    before = pj.read_bytes()
    provision_tree(str(tmp_path), proj, ws)
    assert pj.read_bytes() == before


def test_audit_log_not_truncated(tmp_path):
    proj, ws = _proj_ws(tmp_path)
    provision_tree(str(tmp_path), proj, ws)
    log = tmp_path / ".agentboard" / "audit-log.jsonl"
    log.write_text('{"existing": true}\n', encoding="utf-8", newline="")
    provision_tree(str(tmp_path), proj, ws)
    assert log.read_text(encoding="utf-8") == '{"existing": true}\n'
