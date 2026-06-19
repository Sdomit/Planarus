from fastapi.testclient import TestClient

from app.models.context_file import ContextFile
from sqlmodel import select


def _workspace(client: TestClient, slug: str = "ws") -> str:
    return client.post("/api/v1/workspaces", json={"name": "WS", "slug": slug}).json()["id"]


def test_create_without_folder_provisions_nothing(client):
    ws = _workspace(client)
    proj = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "proj"}
    ).json()
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    assert files == []


def test_relative_folder_path_rejected_422(client):
    ws = _workspace(client)
    res = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": ws,
            "title": "P",
            "slug": "proj",
            "folder_path": "relative/dir",
        },
    )
    assert res.status_code == 422


def test_update_setting_folder_provisions(client, tmp_path):
    ws = _workspace(client)
    proj = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "proj"}
    ).json()
    assert client.get(f"/api/v1/context-files?project_id={proj['id']}").json() == []

    res = client.patch(
        f"/api/v1/projects/{proj['id']}", json={"folder_path": str(tmp_path)}
    )
    assert res.status_code == 200
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    assert len(files) == 16
    assert (tmp_path / "context" / "PROJECT.md").is_file()


def test_create_does_not_break_when_folder_set(client, tmp_path, session):
    """A successful save with a folder commits both the project and its pack."""
    ws = _workspace(client)
    res = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": ws,
            "title": "P",
            "slug": "proj",
            "folder_path": str(tmp_path),
        },
    )
    assert res.status_code == 201
    proj_id = res.json()["id"]
    rows = session.exec(
        select(ContextFile).where(ContextFile.project_id == proj_id)
    ).all()
    assert len(rows) == 16
