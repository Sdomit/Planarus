"""Explicit gated fetch — the one mutation exception (Phase 12b).

Proves the exception stays narrow: disabled by default, control-token-gated,
rate-limited, and — critically — a fetch only advances remote-tracking refs +
FETCH_HEAD, never the local branch or working tree (SHOW, DON'T DO).
"""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_local_control_token
from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.services import git_service

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

TOKEN_HEADER = {"X-Planarus-Local-Token": get_local_control_token()}


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(path) -> None:
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _commit(repo, filename: str, message: str) -> str:
    (repo / filename).write_text("x\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo_with_stale_remote(tmp_path):
    """Build repoA whose origin/main is one commit BEHIND the remote, so a fetch
    has something real to advance. Returns (repoA, commit1, commit2)."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")

    repo_a = tmp_path / "repoA"
    repo_a.mkdir()
    _init_repo(repo_a)
    commit1 = _commit(repo_a, "a.txt", "c1")
    _git(repo_a, "remote", "add", "origin", str(origin))
    _git(repo_a, "push", "-u", "origin", "main")

    # A second clone advances the remote to commit2; repoA doesn't know yet.
    repo_b = tmp_path / "repoB"
    _git(tmp_path, "clone", str(origin), str(repo_b))
    _git(repo_b, "config", "user.email", "b@example.com")
    _git(repo_b, "config", "user.name", "B")
    commit2 = _commit(repo_b, "b.txt", "c2")
    _git(repo_b, "push", "origin", "main")

    return repo_a, commit1, commit2


@pytest.fixture(autouse=True)
def _fresh_state():
    git_service._snapshot_cache.clear()
    git_service._last_fetch_at.clear()
    yield
    git_service._snapshot_cache.clear()
    git_service._last_fetch_at.clear()


@pytest.fixture(name="fetch_enabled")
def _fetch_enabled(monkeypatch):
    monkeypatch.setattr(settings, "git_fetch_enabled", True)


# --- service-level ----------------------------------------------------------

def test_disabled_by_default_raises(tmp_path) -> None:
    from app.core.exceptions import ConflictError

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    with pytest.raises(ConflictError):
        git_service.fetch("proj_1", str(repo))


def test_no_remote(tmp_path, fetch_enabled) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "a.txt", "c1")
    result = git_service.fetch("proj_1", str(repo))
    assert result.status == "no_remote"
    assert result.snapshot is not None  # UI can still refresh the stamp


def test_fetch_ok_advances_remote_ref_but_not_worktree(tmp_path, fetch_enabled) -> None:
    repo_a, commit1, commit2 = _repo_with_stale_remote(tmp_path)
    assert commit1 != commit2

    # Before: repoA's remote-tracking ref is still at commit1.
    assert _git(repo_a, "rev-parse", "refs/remotes/origin/main") == commit1

    result = git_service.fetch("proj_1", str(repo_a))
    assert result.status == "ok", result.message
    assert result.remote == "origin"

    # The remote-tracking ref advanced to commit2 …
    assert _git(repo_a, "rev-parse", "refs/remotes/origin/main") == commit2
    # … but the local branch and working tree are UNTOUCHED (SHOW, DON'T DO).
    assert _git(repo_a, "rev-parse", "HEAD") == commit1
    assert _git(repo_a, "rev-parse", "main") == commit1
    assert not (repo_a / "b.txt").exists()  # commit2's file never entered the tree
    # Snapshot refreshed: main is now behind its upstream by 1, fetch stamp set.
    assert result.snapshot.last_fetched_at is not None


def test_rate_limited_on_immediate_second_call(tmp_path, fetch_enabled) -> None:
    repo_a, _, _ = _repo_with_stale_remote(tmp_path)
    first = git_service.fetch("proj_1", str(repo_a))
    assert first.status == "ok"
    second = git_service.fetch("proj_1", str(repo_a))
    assert second.status == "rate_limited"
    assert "again" in second.message.lower()


def test_missing_folder_degrades(tmp_path, fetch_enabled) -> None:
    result = git_service.fetch("proj_1", str(tmp_path / "nope"))
    assert result.status == "failed"
    assert "missing" in result.message.lower()


def test_run_fetch_rejects_dash_remote(tmp_path) -> None:
    """A remote name that could be read as a flag is refused before git runs."""
    with pytest.raises(ValueError):
        git_service._run_fetch(str(tmp_path), "-x")


def test_run_still_rejects_fetch_verb(tmp_path) -> None:
    """The read-only gate never learned to fetch — the mutation must use the
    separate _run_fetch path."""
    with pytest.raises(ValueError):
        git_service._run(str(tmp_path), ("fetch", "origin"))


# --- endpoint wiring --------------------------------------------------------

def _create_project(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws"}).json()
    res = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "proj"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _point_project_at(session: Session, proj_id: str, path) -> None:
    proj = session.get(Project, proj_id)
    proj.folder_path = str(path)
    session.add(proj)
    session.commit()


def test_endpoint_requires_control_token(client: TestClient, fetch_enabled) -> None:
    proj_id = _create_project(client)
    # No token header → 401, even with fetch enabled.
    assert client.post(f"/api/v1/projects/{proj_id}/git/fetch").status_code == 401


def test_endpoint_disabled_returns_409(client: TestClient) -> None:
    proj_id = _create_project(client)
    res = client.post(f"/api/v1/projects/{proj_id}/git/fetch", headers=TOKEN_HEADER)
    assert res.status_code == 409
    assert "disabled" in res.json()["detail"].lower()


def test_endpoint_not_found(client: TestClient, fetch_enabled) -> None:
    res = client.post("/api/v1/projects/proj_nope/git/fetch", headers=TOKEN_HEADER)
    assert res.status_code == 404


def test_endpoint_fetch_ok_writes_audit(
    client: TestClient, session: Session, tmp_path, fetch_enabled
) -> None:
    repo_a, _, commit2 = _repo_with_stale_remote(tmp_path)
    proj_id = _create_project(client)
    _point_project_at(session, proj_id, repo_a)

    res = client.post(f"/api/v1/projects/{proj_id}/git/fetch", headers=TOKEN_HEADER)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["remote"] == "origin"
    assert body["snapshot"]["is_repo"] is True

    # The outbound action left an audit trail (what a Truth Bar would render).
    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "git_fetch")
    ).all()
    assert len(events) == 1
    assert events[0].project_id == proj_id
    assert events[0].actor_type == "human"
