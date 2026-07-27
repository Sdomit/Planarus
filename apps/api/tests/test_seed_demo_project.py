"""The built-in demo project ships with the tool, so its seed is a shipped path.

``run-planarus.bat`` / ``run-planarus.sh`` run ``scripts/seed_demo_project.py
--auto`` between the migration and the server on every start. A seed that
throws on someone's first launch is a broken install, and one that quietly
stops covering a feature is a demo that undersells the product — so this
asserts both: it runs, and it still touches every surface a new user is
supposed to see.

Loads the script by path (it's an ops script, not a package) the same way
``test_doctor.py`` does.
"""
import importlib.util
import pathlib

import pytest
from app.models.approval_request import ApprovalRequest
from app.models.blocker import Blocker
from app.models.calendar_event import CalendarEvent
from app.models.checklist_item import ChecklistItem
from app.models.comment import Comment
from app.models.context_file import ContextFile
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.entity_connection import EntityConnection
from app.models.link import Link
from app.models.mention import Mention
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.status_option import StatusOption
from app.models.task import Task
from app.models.todo import Todo
from sqlmodel import func, select

_SEED_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_project.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("planarus_seed_demo", _SEED_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _count(session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


@pytest.fixture(name="seeded")
def seeded_fixture(session, tmp_path, monkeypatch):
    """Run the real seed once, with its on-disk pack redirected into tmp_path."""
    seed = _load_seed()
    root = tmp_path / "demo-project"
    root.mkdir()
    monkeypatch.setattr(seed, "_demo_folder", lambda: str(root))
    project = seed._seed(session)
    return seed, project, root


def test_seed_runs_and_creates_the_demo_project(seeded, session):
    seed, project, _root = seeded
    assert project.slug == seed.PROJECT_SLUG
    assert project.status == "active"
    # Reachable in the app: the dashboard renders workspaces[0] only.
    first_workspace = session.exec(select(Project.workspace_id)).first()
    assert project.workspace_id == first_workspace


@pytest.mark.parametrize(
    "model,minimum",
    [
        (Phase, 6),
        (Stage, 3),
        (Task, 12),
        (ChecklistItem, 4),
        (Todo, 4),
        (Milestone, 4),
        (Risk, 4),
        (Decision, 4),
        (Blocker, 2),
        (Doc, 6),
        (Comment, 4),
        (Link, 4),
        (CalendarEvent, 4),
        (EntityConnection, 6),
        (StatusOption, 5),
        (Mention, 4),
        (ApprovalRequest, 4),
        (ContextFile, 10),
    ],
)
def test_every_feature_surface_is_populated(seeded, session, model, minimum):
    """The demo's whole job is showing the product. An empty view undersells it."""
    assert _count(session, model) >= minimum


def test_custom_statuses_cover_every_entity_type_that_supports_them(seeded, session):
    kinds = {o.entity_type for o in session.exec(select(StatusOption))}
    assert kinds == {"task", "phase", "risk", "milestone", "decision"}


def test_every_connection_relation_type_is_demonstrated(seeded, session):
    relations = {c.relation_type for c in session.exec(select(EntityConnection))}
    assert relations == {
        "depends_on",
        "implements",
        "mitigates",
        "contributes_to",
        "references",
        "related_to",
    }


def test_approvals_show_the_whole_lifecycle(seeded, session):
    approvals = list(session.exec(select(ApprovalRequest)))
    statuses = [a.status for a in approvals]
    # Pending ones are the point — that is the queue a new user is meant to act
    # on. Applied and rejected give the history tab and audit trail content.
    assert statuses.count("pending") >= 2
    assert "applied" in statuses
    assert "rejected" in statuses
    applied = next(a for a in approvals if a.status == "applied")
    assert applied.applied_audit_event_id, "an applied proposal must link its audit event"


def test_mentions_produce_real_backlinks(seeded, session):
    """A mention row only exists if the seeded Tiptap JSON is the shape the
    extractor actually parses — this is the guard on that coupling."""
    targets = {m.target_type for m in session.exec(select(Mention))}
    assert {"task", "risk", "decision", "milestone", "phase"} <= targets


def test_canvas_holds_a_real_excalidraw_scene(seeded, session):
    import json

    canvas = session.exec(select(Doc).where(Doc.doc_type == "canvas")).first()
    assert canvas is not None
    assert canvas.editor_format == "excalidraw"
    scene = json.loads(canvas.content_json)
    elements = scene["elements"]
    assert len(elements) >= 6
    # Every element needs an explicit id, or Excalidraw invents one on load and
    # the first render looks like an edit — an autosave on every open.
    assert all(e.get("id") for e in elements)
    # Cards bind back to real entities rather than being anonymous rectangles.
    bound = [e for e in elements if e.get("customData", {}).get("planarusEntity")]
    assert len(bound) >= 3


def test_dated_content_is_relative_so_the_views_are_never_empty(seeded, session):
    """Hardcoded 2026 dates would leave a demo installed later on an empty
    calendar and a silent notification bell."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    starts = [
        datetime.fromisoformat(e.start_at) if len(e.start_at) > 10 else None
        for e in session.exec(select(CalendarEvent))
    ]
    assert any(s and abs(s - now) < timedelta(days=10) for s in starts)

    dues = [t.due_at for t in session.exec(select(Task)) if t.due_at]
    assert any(datetime.fromisoformat(d) < now for d in dues), "one overdue task"
    assert any(datetime.fromisoformat(d) > now for d in dues), "one upcoming task"


def test_context_pack_is_written_to_disk(seeded):
    _seed, _project, root = seeded
    context = root / "context"
    assert (context / "PROJECT.md").exists()
    assert (context / "TASKS.md").exists()
    assert (context / "DECISIONS.md").exists()


def test_seeding_twice_is_a_no_op(seeded, session):
    """The launchers run this on every start; the second one must do nothing."""
    seed, _project, _root = seeded
    assert _count(session, Project) == 1
    assert "already present" in (seed._already_seeded(session) or "")


def test_the_marker_survives_deleting_the_demo(session):
    """Deleting the demo project is a decision the next launch respects rather
    than undoes — otherwise it reappears on every start, forever."""
    from app.services import settings_service

    seed = _load_seed()
    assert seed._already_seeded(session) is None  # nothing seeded, nothing to skip
    settings_service.set_setting(session, seed.SEEDED_KEY, True)
    session.commit()
    assert "has since been deleted" in (seed._already_seeded(session) or "")
