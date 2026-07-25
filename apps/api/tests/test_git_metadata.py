"""Live read-only Git metadata (Phase 8).

The Git state variations are exercised at the service level (``git_service.collect``
is pure given a folder path), which keeps them independent of project
provisioning. The endpoint tests cover the wiring: project lookup, folder
resolution, and the 404 path.
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


def _commit_readme(repo) -> None:
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "first commit")


# --- service-level: Git state variations ----------------------------------

def test_service_no_folder() -> None:
    link = git_service.collect("proj_1", None)
    assert link.is_repo is False
    assert "folder path" in link.message.lower()
    assert link.checked_at


def test_service_missing_folder(tmp_path) -> None:
    link = git_service.collect("proj_1", str(tmp_path / "nope"))
    assert link.is_repo is False
    assert "does not exist" in link.message.lower()


def test_service_not_a_repo(tmp_path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    link = git_service.collect("proj_1", str(plain))
    assert link.is_repo is False
    assert "not a git repository" in link.message.lower()


def test_service_clean_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit_readme(repo)

    link = git_service.collect("proj_1", str(repo))
    assert link.is_repo is True
    assert link.current_branch == "main"
    assert link.detached is False
    assert link.is_dirty is False
    assert link.dirty_count == 0
    assert link.last_commit_subject == "first commit"
    assert link.last_commit_sha
    assert link.message is None


def test_service_dirty_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit_readme(repo)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")  # one untracked file

    link = git_service.collect("proj_1", str(repo))
    assert link.is_dirty is True
    assert link.dirty_count == 1


def test_service_unborn_branch_no_commit(tmp_path) -> None:
    """A freshly-init'd repo has a branch name but no commits yet."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    link = git_service.collect("proj_1", str(repo))
    assert link.is_repo is True
    assert link.current_branch == "main"
    assert link.detached is False
    assert link.last_commit_sha is None
    assert link.last_commit_subject is None


def test_service_detached_head(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit_readme(repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    _git(repo, "checkout", "--detach", sha)
    link = git_service.collect("proj_1", str(repo))
    assert link.is_repo is True
    assert link.detached is True
    assert link.current_branch is None


def test_service_subdir_reports_repo_toplevel(tmp_path) -> None:
    """folder_path inside a repo resolves to the repo root, not the subdir."""
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    _init_repo(repo)
    _commit_readme(repo)
    link = git_service.collect("proj_1", str(repo / "sub"))
    assert link.is_repo is True
    assert link.repo_path.replace("\\", "/").endswith("/repo")


def test_service_remote_url(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "https://example.com/x.git")
    link = git_service.collect("proj_1", str(repo))
    assert link.remote_url == "https://example.com/x.git"


def test_service_remote_url_with_spaces(tmp_path) -> None:
    """A local-path remote containing spaces (common on Windows) is not dropped."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    spaced = r"C:\Users\John Doe\repos\origin.git"
    _git(repo, "remote", "add", "origin", spaced)
    link = git_service.collect("proj_1", str(repo))
    assert link.remote_url == spaced


def test_service_handles_missing_git(monkeypatch, tmp_path) -> None:
    """A missing git binary degrades to is_repo=False, never raises."""
    def _boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(git_service.subprocess, "run", _boom)
    repo = tmp_path / "r"
    repo.mkdir()
    link = git_service.collect("proj_1", str(repo))
    assert link.is_repo is False
    assert "not installed" in link.message.lower()


# --- endpoint wiring -------------------------------------------------------

def _create_project(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws"}).json()
    res = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "proj"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_endpoint_project_without_folder(client: TestClient) -> None:
    proj_id = _create_project(client)
    res = client.get(f"/api/v1/projects/{proj_id}/git")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == proj_id
    assert data["is_repo"] is False
    assert "folder path" in data["message"].lower()


def test_endpoint_reports_real_repo(client: TestClient, session: Session, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit_readme(repo)

    proj_id = _create_project(client)
    # Point the project at the repo directly (bypassing provisioning-on-save,
    # which would write context files and dirty the tree).
    proj = session.get(Project, proj_id)
    proj.folder_path = str(repo)
    session.add(proj)
    session.commit()

    data = client.get(f"/api/v1/projects/{proj_id}/git").json()
    assert data["is_repo"] is True
    assert data["current_branch"] == "main"
    assert data["last_commit_subject"] == "first commit"


def test_endpoint_project_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/proj_nope/git").status_code == 404
