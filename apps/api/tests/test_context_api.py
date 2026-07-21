from fastapi.testclient import TestClient


def _workspace(client: TestClient, slug: str = "ws") -> str:
    res = client.post("/api/v1/workspaces", json={"name": "WS", "slug": slug})
    assert res.status_code == 201
    return res.json()["id"]


def _project_with_folder(client: TestClient, tmp_path, slug: str = "proj") -> dict:
    ws = _workspace(client, slug=f"{slug}-ws")
    res = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": ws,
            "title": "P",
            "slug": slug,
            "folder_path": str(tmp_path),
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_create_with_folder_auto_provisions(client, tmp_path):
    proj = _project_with_folder(client, tmp_path)
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    assert len(files) == 16
    assert (tmp_path / "context" / "PROJECT.md").is_file()
    assert (tmp_path / ".planarus" / "project.json").is_file()


def test_regenerate_endpoint_idempotent(client, tmp_path):
    proj = _project_with_folder(client, tmp_path)
    res = client.post(f"/api/v1/projects/{proj['id']}/context/regenerate")
    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == proj["id"]
    # Already provisioned on create with unchanged data → nothing rewritten.
    assert body["written"] == 0
    assert len(body["outcomes"]) == 16


def test_regenerate_without_folder_400(client):
    ws = _workspace(client)
    proj = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "nofolder"}
    ).json()
    res = client.post(f"/api/v1/projects/{proj['id']}/context/regenerate")
    assert res.status_code == 400


def test_regenerate_unknown_project_404(client):
    res = client.post("/api/v1/projects/proj_nope/context/regenerate")
    assert res.status_code == 404


def test_content_endpoint(client, tmp_path):
    proj = _project_with_folder(client, tmp_path)
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    cf = next(f for f in files if f["relative_path"] == "context/PROJECT.md")
    res = client.get(f"/api/v1/context-files/{cf['id']}/content")
    assert res.status_code == 200
    body = res.json()
    assert body["drifted"] is False
    assert body["content"].startswith("---")


def test_diff_empty_when_clean(client, tmp_path):
    proj = _project_with_folder(client, tmp_path)
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    cf = next(f for f in files if f["relative_path"] == "context/PROJECT.md")
    res = client.get(f"/api/v1/context-files/{cf['id']}/diff")
    assert res.status_code == 200
    assert res.json()["diff"] == ""


def test_pin_toggle(client, tmp_path):
    proj = _project_with_folder(client, tmp_path)
    files = client.get(f"/api/v1/context-files?project_id={proj['id']}").json()
    cf = files[0]
    res = client.patch(f"/api/v1/context-files/{cf['id']}", json={"pinned": True})
    assert res.status_code == 200
    assert res.json()["pinned"] is True


def test_content_unknown_404(client):
    res = client.get("/api/v1/context-files/ctx_nope/content")
    assert res.status_code == 404
