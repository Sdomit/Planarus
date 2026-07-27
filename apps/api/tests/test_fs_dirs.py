"""Local folder-picker listing (Phase 12d): names only, local mode only."""
from app.core.config import settings
from app.core.security import get_local_control_token
from fastapi.testclient import TestClient

TOKEN_HEADER = {"X-Planarus-Local-Token": get_local_control_token()}


def test_requires_control_token(client: TestClient) -> None:
    assert client.get("/api/v1/fs/dirs").status_code == 401


def test_team_mode_409(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    res = client.get("/api/v1/fs/dirs", headers=TOKEN_HEADER)
    assert res.status_code == 409
    assert "team" in res.json()["detail"].lower()


def test_default_lists_home(client: TestClient) -> None:
    res = client.get("/api/v1/fs/dirs", headers=TOKEN_HEADER)
    assert res.status_code == 200
    body = res.json()
    assert body["path"]
    assert body["roots"]
    assert body["message"] is None


def test_lists_subdirs_with_git_badge(client: TestClient, tmp_path) -> None:
    base = tmp_path / "browse"  # conftest plants other dirs in tmp_path itself
    base.mkdir()
    (base / "plain").mkdir()
    repo = base / "repo"
    (repo / ".git").mkdir(parents=True)
    (base / ".hidden").mkdir()
    (base / "file.txt").write_text("x", encoding="utf-8")

    res = client.get("/api/v1/fs/dirs", params={"path": str(base)}, headers=TOKEN_HEADER)
    assert res.status_code == 200
    body = res.json()
    names = [d["name"] for d in body["dirs"]]
    assert names == ["plain", "repo"]  # sorted; hidden dirs and files excluded
    by_name = {d["name"]: d for d in body["dirs"]}
    assert by_name["repo"]["is_git"] is True
    assert by_name["plain"]["is_git"] is False
    assert body["parent"]


def test_missing_path_degrades(client: TestClient, tmp_path) -> None:
    res = client.get(
        "/api/v1/fs/dirs", params={"path": str(tmp_path / "nope")}, headers=TOKEN_HEADER
    )
    assert res.status_code == 200
    assert res.json()["message"]
