"""Repo cockpit snapshot (Phase 12a).

Same split as ``test_git_metadata``: Git state variations at the service level
(``git_service.snapshot`` is pure given a folder path), endpoint tests for the
wiring only. Test-side git mutations (checkout, push, fetch, ...) are fine —
the read-only guarantee applies to app code, which ``test_git_readonly`` scans.
"""
import shutil
import subprocess

import pytest
from app.models.project import Project
from app.services import git_service
from fastapi.testclient import TestClient
from sqlmodel import Session

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path) -> None:
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _commit(repo, filename: str, message: str) -> None:
    (repo / filename).write_text("x\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)


def _by_name(snap, name):
    return next(b for b in snap.branches if b.name == name)


@pytest.fixture(autouse=True)
def _fresh_snapshot_cache():
    git_service._snapshot_cache.clear()
    yield
    git_service._snapshot_cache.clear()


# --- service-level ----------------------------------------------------------

def test_not_a_repo(tmp_path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    snap = git_service.snapshot("proj_1", str(plain))
    assert snap.is_repo is False
    assert "not a git repository" in snap.message.lower()
    assert snap.branches == [] and snap.branches_total == 0


def test_single_branch_clean(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")

    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.is_repo is True
    assert snap.current_branch == "main"
    assert snap.detached is False
    assert snap.default_branch == "main"  # fallback path — no origin/HEAD
    assert snap.branches_total == 1
    branch = _by_name(snap, "main")
    assert branch.is_current is True
    assert branch.upstream is None
    assert branch.ahead is None and branch.behind is None  # no upstream ⇒ unknown
    assert branch.ahead_of_default == 0 and branch.behind_default == 0
    assert snap.needs_merge == []
    tree = snap.working_tree
    assert (tree.staged, tree.unstaged, tree.untracked, tree.conflicted) == (0, 0, 0, 0)
    assert tree.ahead is None and tree.behind is None
    assert snap.last_fetched_at is None  # never fetched
    assert snap.last_commit_subject == "first commit"
    assert snap.message is None


def test_feature_branch_divergence_and_needs_merge(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "a.txt", "c1")
    _git(repo, "checkout", "-b", "feat")
    _commit(repo, "b.txt", "c2")
    _git(repo, "checkout", "main")
    _commit(repo, "c.txt", "c3")

    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.default_branch == "main"
    assert snap.branches_total == 2
    assert snap.needs_merge == ["feat"]
    feat = _by_name(snap, "feat")
    assert feat.is_current is False
    assert feat.ahead_of_default == 1  # c2
    assert feat.behind_default == 1  # c3
    main = _by_name(snap, "main")
    assert main.is_current is True
    assert main.ahead_of_default == 0 and main.behind_default == 0


def test_working_tree_counts(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")
    (repo / "staged.txt").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")  # unstaged edit
    (repo / "loose.txt").write_text("u\n", encoding="utf-8")  # untracked

    tree = git_service.snapshot("proj_1", str(repo)).working_tree
    assert tree.staged == 1
    assert tree.unstaged == 1
    assert tree.untracked == 1
    assert tree.conflicted == 0


def test_upstream_ahead_and_fetch_stamp(tmp_path) -> None:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-b", "main")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    _git(repo, "remote", "set-head", "origin", "--auto")  # origin/HEAD ⇒ rev-parse path
    _git(repo, "fetch", "origin")
    _commit(repo, "next.txt", "local only")  # ahead of upstream by 1

    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.default_branch == "main"
    branch = _by_name(snap, "main")
    assert branch.upstream == "origin/main"
    assert branch.ahead == 1 and branch.behind == 0
    assert branch.gone is False
    assert snap.working_tree.ahead == 1 and snap.working_tree.behind == 0
    assert snap.last_fetched_at is not None


def test_branch_cap(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")
    for i in range(3):
        _git(repo, "branch", f"b{i}")

    monkeypatch.setattr(git_service, "_BRANCH_CAP", 2)
    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.branches_total == 4
    assert len(snap.branches) == 2


def test_detached_head(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    _git(repo, "checkout", "--detach", sha)

    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.is_repo is True
    assert snap.detached is True
    assert snap.current_branch is None


def test_snapshot_is_ttl_cached(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")

    first = git_service.snapshot("proj_1", str(repo))
    (repo / "new.txt").write_text("x\n", encoding="utf-8")
    assert git_service.snapshot("proj_1", str(repo)) is first  # within TTL
    git_service._snapshot_cache.clear()
    assert git_service.snapshot("proj_1", str(repo)).working_tree.untracked == 1


def test_handles_missing_git(monkeypatch, tmp_path) -> None:
    def _boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(git_service.subprocess, "run", _boom)
    repo = tmp_path / "r"
    repo.mkdir()
    snap = git_service.snapshot("proj_1", str(repo))
    assert snap.is_repo is False
    assert "not installed" in snap.message.lower()


# --- endpoint wiring --------------------------------------------------------

def _create_project(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws"}).json()
    res = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "proj"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_endpoint_reports_snapshot(client: TestClient, session: Session, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit(repo, "README.md", "first commit")

    proj_id = _create_project(client)
    proj = session.get(Project, proj_id)
    proj.folder_path = str(repo)
    session.add(proj)
    session.commit()

    data = client.get(f"/api/v1/projects/{proj_id}/git/snapshot").json()
    assert data["is_repo"] is True
    assert data["current_branch"] == "main"
    assert data["default_branch"] == "main"
    assert data["branches_total"] == 1
    assert data["branches"][0]["name"] == "main"
    assert data["working_tree"]["untracked"] == 0


def test_endpoint_project_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/proj_nope/git/snapshot").status_code == 404
