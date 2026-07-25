import json

from app.fsmemory.regenerator import regenerate
from app.fsmemory.spec import CONTEXT_FILES
from app.models.audit_event import AuditEvent
from app.models.context_file import ContextFile
from app.models.project import Project
from app.models.workspace import Workspace
from sqlmodel import select

_TS = "2026-06-19T00:00:00+00:00"


def _seed(session, root):
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
    session.add(ws)
    session.commit()
    session.add(proj)
    session.commit()
    return proj, ws


def test_creates_all_files_and_rows(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    report = regenerate(session, proj, ws, now="2026-06-19T01:00:00+00:00")
    session.commit()

    assert report.written_count == len(CONTEXT_FILES)
    for spec in CONTEXT_FILES:
        assert (tmp_path / spec.relative_path).is_file(), spec.filename

    rows = session.exec(
        select(ContextFile).where(ContextFile.project_id == "proj_1")
    ).all()
    assert len(rows) == len(CONTEXT_FILES)
    assert all(r.token_estimate and r.token_estimate > 0 for r in rows)


def test_idempotent_second_run(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    md_snap = {
        spec.relative_path: (tmp_path / spec.relative_path).read_bytes()
        for spec in CONTEXT_FILES
    }
    json_snap = {
        name: (tmp_path / ".planarus" / name).read_bytes()
        for name in ("project.json", "workspace-link.json", "settings.json")
    }

    report2 = regenerate(session, proj, ws, now="t2")
    session.commit()

    assert report2.written_count == 0
    for spec in CONTEXT_FILES:
        assert (tmp_path / spec.relative_path).read_bytes() == md_snap[spec.relative_path]
    for name, data in json_snap.items():
        assert (tmp_path / ".planarus" / name).read_bytes() == data


def test_pinned_file_skipped(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    row = session.exec(
        select(ContextFile).where(ContextFile.relative_path == "context/NEXT_STEP.md")
    ).one()
    row.pinned = True
    session.add(row)
    session.commit()

    target = tmp_path / "context" / "NEXT_STEP.md"
    target.write_text("PINNED MANUAL CONTENT\n", encoding="utf-8", newline="")

    report = regenerate(session, proj, ws, now="t2")
    session.commit()

    assert target.read_text(encoding="utf-8") == "PINNED MANUAL CONTENT\n"
    outcomes = {o.relative_path: o for o in report.outcomes}
    assert outcomes["context/NEXT_STEP.md"].status == "pinned-skip"


def test_drifted_file_not_overwritten(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    target = tmp_path / "context" / "STATUS.md"
    target.write_text("MANUAL EDIT\n", encoding="utf-8", newline="")

    report = regenerate(session, proj, ws, now="t2")
    session.commit()

    assert target.read_text(encoding="utf-8") == "MANUAL EDIT\n"
    row = session.exec(
        select(ContextFile).where(ContextFile.relative_path == "context/STATUS.md")
    ).one()
    assert row.last_manual_edit_at == "t2"
    outcomes = {o.relative_path: o for o in report.outcomes}
    assert outcomes["context/STATUS.md"].status == "drift-skip"
    assert outcomes["context/STATUS.md"].drifted is True


def test_changed_data_rewrites(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    proj.status = "active"
    proj.updated_at = "2026-06-20T00:00:00+00:00"
    session.add(proj)
    session.commit()

    report = regenerate(session, proj, ws, now="t2")
    session.commit()

    assert report.written_count >= 1
    assert "active" in (tmp_path / "context" / "STATUS.md").read_text(encoding="utf-8")


def test_missing_file_recreated(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    (tmp_path / "context" / "PROJECT.md").unlink()
    report = regenerate(session, proj, ws, now="t2")
    session.commit()

    assert (tmp_path / "context" / "PROJECT.md").is_file()
    outcomes = {o.relative_path: o for o in report.outcomes}
    assert outcomes["context/PROJECT.md"].status in {"created", "written"}


def test_authored_file_not_clobbered_on_first_regen(session, tmp_path):
    """Fresh checkout: a hand-written authored file exists on disk with no row yet.
    The first regen must adopt it verbatim (not overwrite with the stub) and pin it."""
    proj, ws = _seed(session, tmp_path)
    (tmp_path / "context").mkdir()
    hand_written = "---\npinned: true\n---\n\n# Real objective\n\nShip the thing.\n"
    target = tmp_path / "context" / "NEXT_STEP.md"
    target.write_text(hand_written, encoding="utf-8", newline="")

    report = regenerate(session, proj, ws, now="t1")
    session.commit()

    # Content preserved, not replaced by the "_No next-step objective_" stub.
    assert target.read_text(encoding="utf-8") == hand_written
    outcomes = {o.relative_path: o for o in report.outcomes}
    assert outcomes["context/NEXT_STEP.md"].status == "pinned-skip"
    row = session.exec(
        select(ContextFile).where(ContextFile.relative_path == "context/NEXT_STEP.md")
    ).one()
    assert row.pinned is True  # adopted + pinned so future regens skip it


def test_authored_legacy_unpinned_row_migrated(session, tmp_path):
    """A row created before the `authored` flag (pinned=False) is auto-pinned on
    the next regen, and hand edits made after are then preserved."""
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    row = session.exec(
        select(ContextFile).where(ContextFile.relative_path == "context/NEXT_STEP.md")
    ).one()
    row.pinned = False  # simulate a legacy row predating the authored flag
    session.add(row)
    session.commit()

    edited = "# My own next step\n"
    target = tmp_path / "context" / "NEXT_STEP.md"
    target.write_text(edited, encoding="utf-8", newline="")

    regenerate(session, proj, ws, now="t2")
    session.commit()

    assert target.read_text(encoding="utf-8") == edited
    session.refresh(row)
    assert row.pinned is True


def test_data_driven_file_still_regenerates(session, tmp_path):
    """authored=False files (e.g. STATUS.md) keep regenerating on data change."""
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    proj.status = "active"
    proj.updated_at = "2026-06-20T00:00:00+00:00"
    session.add(proj)
    session.commit()

    regenerate(session, proj, ws, now="t2")
    session.commit()
    assert "active" in (tmp_path / "context" / "STATUS.md").read_text(encoding="utf-8")


def test_audit_event_and_log_line(session, tmp_path):
    proj, ws = _seed(session, tmp_path)
    regenerate(session, proj, ws, now="t1")
    session.commit()

    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "context_regen")
    ).all()
    assert len(events) == 1

    log_lines = (
        (tmp_path / ".planarus" / "audit-log.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(log_lines) == 1
    entry = json.loads(log_lines[0])
    assert entry["event_type"] == "context_regen"
    assert entry["summary"]["written"] == len(CONTEXT_FILES)
