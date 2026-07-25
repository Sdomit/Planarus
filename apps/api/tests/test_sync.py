"""Phase 10.6 — sync manifest + three-way conflict detection."""
import pytest
from app.sync import (
    ChangeKind,
    build_manifest,
    entity_signature,
    resolve_conflicts,
    three_way_diff,
)

K = ("task", "t1")


# --- three-way diff -----------------------------------------------------------
def test_no_change_is_empty_plan():
    m = {K: "a"}
    assert three_way_diff(m, m, m).changes == []


def test_local_only_update_propagates_to_remote():
    plan = three_way_diff({K: "a"}, {K: "b"}, {K: "a"})
    assert [c.kind for c in plan.changes] == [ChangeKind.LOCAL_UPDATE]
    assert plan.to_remote() == plan.changes
    assert plan.to_local() == []
    assert not plan.has_conflicts


def test_remote_only_update_propagates_to_local():
    plan = three_way_diff({K: "a"}, {K: "a"}, {K: "b"})
    assert [c.kind for c in plan.changes] == [ChangeKind.REMOTE_UPDATE]
    assert plan.to_local() == plan.changes


def test_convergent_edit_is_not_a_conflict():
    # Both sides made the SAME change → identical signatures → no-op.
    plan = three_way_diff({K: "a"}, {K: "b"}, {K: "b"})
    assert plan.changes == []


def test_divergent_edit_is_a_conflict():
    plan = three_way_diff({K: "a"}, {K: "b"}, {K: "c"})
    assert plan.has_conflicts
    assert plan.conflicts[0].key == K


def test_creates_and_deletes():
    # local create
    assert three_way_diff({}, {K: "a"}, {}).changes[0].kind is ChangeKind.LOCAL_CREATE
    # remote delete
    assert (
        three_way_diff({K: "a"}, {K: "a"}, {}).changes[0].kind
        is ChangeKind.REMOTE_DELETE
    )
    # delete on one side, edit on the other → conflict
    assert three_way_diff({K: "a"}, {}, {K: "b"}).changes[0].kind is ChangeKind.CONFLICT


def test_resolve_conflicts_requires_explicit_choice():
    plan = three_way_diff({K: "a"}, {K: "b"}, {K: "c"})
    # Unresolved conflict must raise — a plan can't be silently applied.
    with pytest.raises(ValueError, match="unresolved conflict"):
        resolve_conflicts(plan, {})
    # Choosing a side turns it into a concrete one-sided change.
    assert resolve_conflicts(plan, {K: "local"}).changes[0].kind is ChangeKind.LOCAL_UPDATE
    assert (
        resolve_conflicts(plan, {K: "remote"}).changes[0].kind
        is ChangeKind.REMOTE_UPDATE
    )


# --- manifest / content signature ---------------------------------------------
def test_manifest_signature_tracks_content_not_timestamps(session):
    from app.schemas.project import ProjectCreate
    from app.schemas.task import TaskCreate
    from app.schemas.workspace import WorkspaceCreate
    from app.services import project_service, task_service, workspace_service

    ws = workspace_service.create_workspace(
        session, WorkspaceCreate(name="W", slug="acme")
    )
    project = project_service.create_project(
        session, ProjectCreate(workspace_id=ws.id, title="P", slug="proj")
    )
    task = task_service.create_task(session, project.id, TaskCreate(title="orig"))

    m1 = build_manifest(session, project.id)
    assert ("project", project.id) in m1
    assert ("task", task.id) in m1

    # A content change flips the signature.
    task.title = "changed"
    session.add(task)
    session.commit()
    m2 = build_manifest(session, project.id)
    assert m2[("task", task.id)] != m1[("task", task.id)]

    # A timestamp-only touch does NOT (created_at/updated_at are excluded).
    sig_before = entity_signature(session.get(type(task), task.id))
    task.updated_at = "2099-01-01T00:00:00+00:00"
    session.add(task)
    session.commit()
    assert entity_signature(session.get(type(task), task.id)) == sig_before
