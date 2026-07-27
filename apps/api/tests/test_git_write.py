"""Gated commit + merge (Phase 12d).

Proves the second exception stays as narrow as the first: disabled by default
behind its own flag, control-token-gated, allowlist-enforced, dirty trees
refused for merge, conflicts aborted so the repo is never left half-merged.
"""
import shutil
import subprocess

import pytest
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.security import get_local_control_token
from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.services import git_service
from fastapi.testclient import TestClient
from sqlmodel import Session, select

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


def _commit(repo, filename: str, message: str, content: str = "x\n") -> str:
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "a.txt", "c1")
    return repo


def _repo_with_feature(tmp_path):
    """main + a `feature` branch one commit ahead, main checked out."""
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "f.txt", "feature work")
    _git(repo, "checkout", "main")
    return repo


@pytest.fixture(autouse=True)
def _fresh_state():
    git_service._snapshot_cache.clear()
    yield
    git_service._snapshot_cache.clear()


@pytest.fixture(name="write_enabled")
def _write_enabled(monkeypatch):
    monkeypatch.setattr(settings, "git_write_enabled", True)


# --- gates ------------------------------------------------------------------

def test_commit_disabled_by_default_raises(tmp_path) -> None:
    with pytest.raises(ConflictError):
        git_service.commit("proj_1", str(_repo(tmp_path)), "msg")


def test_merge_disabled_by_default_raises(tmp_path) -> None:
    with pytest.raises(ConflictError):
        git_service.merge("proj_1", str(_repo(tmp_path)), "feature")


def test_fetch_flag_does_not_enable_writes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "git_fetch_enabled", True)
    with pytest.raises(ConflictError):
        git_service.commit("proj_1", str(_repo(tmp_path)), "msg")


def test_run_still_rejects_write_verbs(tmp_path) -> None:
    for argv in (("commit", "-m", "x"), ("add", "-A"), ("merge", "main")):
        with pytest.raises(ValueError):
            git_service._run(str(tmp_path), argv)


def test_run_write_rejects_unlisted_verbs(tmp_path) -> None:
    for argv in (("push", "origin"), ("checkout", "main"), ("reset", "--hard")):
        with pytest.raises(ValueError):
            git_service._run_write(str(tmp_path), argv)


# --- commit -----------------------------------------------------------------

def test_commit_ok_stages_everything(tmp_path, write_enabled) -> None:
    repo = _repo(tmp_path)
    (repo / "new.txt").write_text("n\n", encoding="utf-8")
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")

    result = git_service.commit("proj_1", str(repo), "  demo commit  ")
    assert result.status == "ok", result.message
    assert result.sha
    assert _git(repo, "log", "-1", "--format=%s") == "demo commit"
    assert _git(repo, "status", "--porcelain") == ""
    assert result.snapshot is not None and result.snapshot.working_tree.untracked == 0


def test_commit_clean_tree_is_noop(tmp_path, write_enabled) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    result = git_service.commit("proj_1", str(repo), "msg")
    assert result.status == "clean"
    assert _git(repo, "rev-parse", "HEAD") == head


def test_commit_empty_message_refused(tmp_path, write_enabled) -> None:
    repo = _repo(tmp_path)
    (repo / "new.txt").write_text("n\n", encoding="utf-8")
    result = git_service.commit("proj_1", str(repo), "   ")
    assert result.status == "failed"
    assert "message" in result.message.lower()
    assert _git(repo, "status", "--porcelain") != ""  # nothing was staged away


def test_commit_missing_folder_degrades(tmp_path, write_enabled) -> None:
    result = git_service.commit("proj_1", str(tmp_path / "nope"), "msg")
    assert result.status == "failed"


# --- merge ------------------------------------------------------------------

def test_merge_ok_fast_forward(tmp_path, write_enabled) -> None:
    repo = _repo_with_feature(tmp_path)
    feature_sha = _git(repo, "rev-parse", "feature")
    result = git_service.merge("proj_1", str(repo), "feature")
    assert result.status == "ok", result.message
    assert _git(repo, "rev-parse", "HEAD") == feature_sha
    assert (repo / "f.txt").exists()


def test_merge_dirty_tree_refused(tmp_path, write_enabled) -> None:
    repo = _repo_with_feature(tmp_path)
    (repo / "a.txt").write_text("uncommitted\n", encoding="utf-8")
    head = _git(repo, "rev-parse", "HEAD")
    result = git_service.merge("proj_1", str(repo), "feature")
    assert result.status == "dirty"
    assert _git(repo, "rev-parse", "HEAD") == head


def test_merge_conflict_is_aborted(tmp_path, write_enabled) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "a.txt", "feature side", content="feature\n")
    _git(repo, "checkout", "main")
    _commit(repo, "a.txt", "main side", content="main\n")
    head = _git(repo, "rev-parse", "HEAD")

    result = git_service.merge("proj_1", str(repo), "feature")
    assert result.status == "conflict"
    # Aborted: HEAD unmoved, no merge in progress, tree clean again.
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "status", "--porcelain") == ""


def test_merge_current_branch_refused(tmp_path, write_enabled) -> None:
    repo = _repo_with_feature(tmp_path)
    assert git_service.merge("proj_1", str(repo), "main").status == "failed"


def test_merge_unknown_branch_refused(tmp_path, write_enabled) -> None:
    repo = _repo_with_feature(tmp_path)
    result = git_service.merge("proj_1", str(repo), "nope")
    assert result.status == "failed"
    assert "not a local branch" in result.message


def test_merge_dash_branch_refused(tmp_path, write_enabled) -> None:
    repo = _repo_with_feature(tmp_path)
    assert git_service.merge("proj_1", str(repo), "-x").status == "failed"


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


def test_endpoints_require_control_token(client: TestClient, write_enabled) -> None:
    proj_id = _create_project(client)
    assert client.post(
        f"/api/v1/projects/{proj_id}/git/commit", json={"message": "m"}
    ).status_code == 401
    assert client.post(
        f"/api/v1/projects/{proj_id}/git/merge", json={"branch": "b"}
    ).status_code == 401


def test_endpoints_disabled_return_409(client: TestClient) -> None:
    proj_id = _create_project(client)
    for path, body in (("commit", {"message": "m"}), ("merge", {"branch": "b"})):
        res = client.post(
            f"/api/v1/projects/{proj_id}/git/{path}", json=body, headers=TOKEN_HEADER
        )
        assert res.status_code == 409
        assert "disabled" in res.json()["detail"].lower()


def test_commit_endpoint_ok_writes_audit(
    client: TestClient, session: Session, tmp_path, write_enabled
) -> None:
    repo = _repo(tmp_path)
    (repo / "new.txt").write_text("n\n", encoding="utf-8")
    proj_id = _create_project(client)
    _point_project_at(session, proj_id, repo)

    res = client.post(
        f"/api/v1/projects/{proj_id}/git/commit",
        json={"message": "from the cockpit"},
        headers=TOKEN_HEADER,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"

    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "git_commit")
    ).all()
    assert len(events) == 1


def test_merge_endpoint_ok_writes_audit(
    client: TestClient, session: Session, tmp_path, write_enabled
) -> None:
    repo = _repo_with_feature(tmp_path)
    proj_id = _create_project(client)
    _point_project_at(session, proj_id, repo)

    res = client.post(
        f"/api/v1/projects/{proj_id}/git/merge",
        json={"branch": "feature"},
        headers=TOKEN_HEADER,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"

    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "git_merge")
    ).all()
    assert len(events) == 1
