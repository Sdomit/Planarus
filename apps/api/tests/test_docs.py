"""Backend tests for Phase 5 Doc CRUD and Markdown export."""
import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient


_EMPTY_JSON = '{"type": "doc", "content": [{"type": "paragraph"}]}'


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-doc"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-doc"},
    ).json()
    return ws["id"], proj["id"]


def _seed_with_folder(client: TestClient, tmp_path) -> tuple[str, str]:
    ws, pid = _seed(client)
    folder = str(tmp_path / "project")
    os.makedirs(folder)
    client.patch(f"/api/v1/projects/{pid}", json={"folder_path": folder})
    return ws, pid


# ---------------------------------------------------------------------------
# List / empty state
# ---------------------------------------------------------------------------


def test_list_docs_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/docs")
    assert res.status_code == 200
    assert res.json() == []


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_doc_minimal(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "My Doc", "doc_type": "note"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "My Doc"
    assert data["doc_type"] == "note"
    assert data["status"] == "draft"
    assert data["version"] == 1
    assert data["id"].startswith("doc_")
    assert data["slug"] == "my-doc"
    assert data["content_json"] == _EMPTY_JSON
    assert data["markdown_cache"] == ""
    assert data["editor_format"] == "tiptap_json"  # default when omitted
    assert data["project_id"] == pid


def test_create_canvas_doc(client: TestClient) -> None:
    """Phase 13: editor_format='excalidraw' creates a canvas seeded with an
    empty, parseable Excalidraw scene."""
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Board", "doc_type": "canvas", "editor_format": "excalidraw"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["doc_type"] == "canvas"
    assert data["editor_format"] == "excalidraw"
    scene = json.loads(data["content_json"])
    assert scene["type"] == "excalidraw"
    assert scene["elements"] == []


def test_create_doc_rejects_unknown_editor_format(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "X", "doc_type": "note", "editor_format": "bogus"},
    )
    assert res.status_code == 422


def test_create_doc_all_types(client: TestClient) -> None:
    _, pid = _seed(client)
    for doc_type in ["note", "spec", "research", "plan", "reference", "other"]:
        res = client.post(
            f"/api/v1/projects/{pid}/docs",
            json={"title": f"Doc {doc_type}", "doc_type": doc_type},
        )
        assert res.status_code == 201, f"Failed for {doc_type}"


def test_create_doc_invalid_type(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Bad", "doc_type": "invalid"},
    )
    assert res.status_code == 422


def test_create_doc_missing_title(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"doc_type": "note"},
    )
    assert res.status_code == 422


def test_create_doc_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_missing/docs",
        json={"title": "X", "doc_type": "note"},
    )
    assert res.status_code == 404


def test_create_doc_slug_deduplication(client: TestClient) -> None:
    _, pid = _seed(client)
    r1 = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Hello World", "doc_type": "note"},
    )
    r2 = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Hello World", "doc_type": "spec"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["slug"] != r2.json()["slug"]
    assert r2.json()["slug"].startswith("hello-world")


def test_create_doc_custom_slug(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "My Doc", "doc_type": "note", "slug": "custom-slug"},
    )
    assert res.status_code == 201
    assert res.json()["slug"] == "custom-slug"


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


def test_get_doc(client: TestClient) -> None:
    _, pid = _seed(client)
    created = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Full Doc", "doc_type": "spec"},
    ).json()
    res = client.get(f"/api/v1/docs/{created['id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == created["id"]
    assert "content_json" in data
    assert "markdown_cache" in data
    assert "version" in data


def test_get_doc_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/docs/doc_missing")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# List — filtering
# ---------------------------------------------------------------------------


def test_list_docs_filter_type(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "Note", "doc_type": "note"}
    )
    client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "Spec", "doc_type": "spec"}
    )
    res = client.get(f"/api/v1/projects/{pid}/docs?doc_type=note")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["doc_type"] == "note"
    # Verify list items do NOT include content_json (DocSummary)
    assert "content_json" not in items[0]


def test_list_docs_returns_truncated_excerpt(client: TestClient) -> None:
    """Note cards preview the body: excerpt mirrors markdown_cache, capped at 280."""
    _, pid = _seed(client)
    doc = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "Groceries", "doc_type": "note"}
    ).json()
    assert client.get(f"/api/v1/projects/{pid}/docs").json()[0]["excerpt"] == ""

    body = "x" * 400
    res = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={
            "content_json": '{"type": "doc", "content": []}',
            "markdown_cache": body,
            "version": doc["version"],
        },
    )
    assert res.status_code == 200

    item = client.get(f"/api/v1/projects/{pid}/docs").json()[0]
    assert item["excerpt"] == "x" * 280
    # The preview is derived, never a second stored copy of the body.
    assert "markdown_cache" not in item


def test_doc_color_set_clear_and_reject(client: TestClient) -> None:
    """0028 swatches: default NULL, set a key, clear with 'default', reject junk."""
    _, pid = _seed(client)
    doc = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "Idea", "doc_type": "note"}
    ).json()
    assert doc["color"] is None

    res = client.patch(f"/api/v1/docs/{doc['id']}", json={"color": "teal", "version": 1})
    assert res.status_code == 200
    assert res.json()["color"] == "teal"
    assert client.get(f"/api/v1/projects/{pid}/docs").json()[0]["color"] == "teal"

    # The sentinel clears it — None on a PATCH field means "unchanged".
    res = client.patch(f"/api/v1/docs/{doc['id']}", json={"color": "default", "version": 2})
    assert res.status_code == 200
    assert res.json()["color"] is None

    # An unknown key never reaches the DOM as a class/attribute value.
    bad = client.patch(f"/api/v1/docs/{doc['id']}", json={"color": "chartreuse", "version": 3})
    assert bad.status_code == 422


def test_list_docs_filter_status(client: TestClient) -> None:
    _, pid = _seed(client)
    d1 = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "D1", "doc_type": "note"}
    ).json()
    client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "D2", "doc_type": "note", "status": "published"},
    )
    res = client.get(f"/api/v1/projects/{pid}/docs?status=draft")
    assert all(d["status"] == "draft" for d in res.json())


def test_list_docs_excludes_archived_by_default(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "A", "doc_type": "note"}
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "archived_at": "2026-06-20T00:00:00+00:00"},
    )
    res = client.get(f"/api/v1/projects/{pid}/docs")
    assert res.json() == []


def test_list_docs_include_archived(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "A", "doc_type": "note"}
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "archived_at": "2026-06-20T00:00:00+00:00"},
    )
    res = client.get(f"/api/v1/projects/{pid}/docs?include_archived=true")
    assert len(res.json()) == 1


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------


def test_update_doc_title(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "Old", "doc_type": "note"}
    ).json()
    res = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "title": "New"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["version"] == 2


def test_update_doc_content(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "C", "doc_type": "note"}
    ).json()
    new_json = '{"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}]}'
    res = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": new_json, "markdown_cache": "hello"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["content_json"] == new_json
    assert data["markdown_cache"] == "hello"
    assert data["version"] == 2


def test_update_doc_content_without_cache_fails(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "C", "doc_type": "note"}
    ).json()
    res = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON},
    )
    assert res.status_code == 422


def test_update_doc_stale_version_409(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "V", "doc_type": "note"}
    ).json()
    # First update succeeds → version 2
    client.patch(f"/api/v1/docs/{d['id']}", json={"version": 1, "title": "V2"})
    # Second update with stale version 1 → 409
    res = client.patch(
        f"/api/v1/docs/{d['id']}", json={"version": 1, "title": "V3"}
    )
    assert res.status_code == 409


def test_update_doc_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/docs/doc_missing", json={"version": 1, "title": "X"})
    assert res.status_code == 404


def test_update_doc_invalid_content_json(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "C", "doc_type": "note"}
    ).json()
    res = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": "not json{{", "markdown_cache": ""},
    )
    assert res.status_code == 422


def test_update_doc_content_too_large(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "C", "doc_type": "note"}
    ).json()
    big = "x" * (2 * 1024 * 1024 + 1)
    res = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": big, "markdown_cache": ""},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def test_export_doc_no_folder(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Export", "doc_type": "note"},
    ).json()
    res = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert res.status_code == 422


def test_export_doc_creates_file(client: TestClient, tmp_path) -> None:
    _, pid = _seed_with_folder(client, tmp_path)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "My Note", "doc_type": "note"},
    ).json()
    # Set markdown content
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "# Hello"},
    )
    res = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert res.status_code == 200
    data = res.json()
    assert data["was_changed"] is True
    assert data["drift_detected"] is False
    assert "my-note" in data["export_path"]
    # Verify file on disk
    folder = str(tmp_path / "project")
    disk_path = os.path.join(folder, data["export_path"])
    assert os.path.exists(disk_path)
    with open(disk_path, encoding="utf-8") as f:
        content = f.read()
    assert "Hello" in content


def test_export_doc_idempotent(client: TestClient, tmp_path) -> None:
    _, pid = _seed_with_folder(client, tmp_path)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Idem", "doc_type": "note"},
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "same"},
    )
    r1 = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    r2 = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert r1.json()["was_changed"] is True
    assert r2.json()["was_changed"] is False


def test_export_doc_drift_returns_409(client: TestClient, tmp_path) -> None:
    _, pid = _seed_with_folder(client, tmp_path)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Drift", "doc_type": "note"},
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "original"},
    )
    r = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert r.json()["was_changed"] is True

    # Manually edit the file on disk to simulate external change
    folder = str(tmp_path / "project")
    disk_path = os.path.join(folder, r.json()["export_path"])
    with open(disk_path, "w", encoding="utf-8") as f:
        f.write("externally modified")

    # Export must detect drift and return 409 without overwriting
    r2 = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert r2.status_code == 409
    assert "changed outside Approvo" in r2.json()["detail"]

    # File on disk still has external content (was NOT overwritten)
    with open(disk_path, encoding="utf-8") as f:
        assert "externally modified" in f.read()


def test_export_doc_drift_force_param_not_accepted(client: TestClient, tmp_path) -> None:
    """?force=true is not a supported parameter — drift always returns 409."""
    _, pid = _seed_with_folder(client, tmp_path)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Force", "doc_type": "note"},
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "original"},
    )
    r = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    export_path = r.json()["export_path"]
    folder = str(tmp_path / "project")
    disk_path = os.path.join(folder, export_path)

    # Create drift
    with open(disk_path, "w", encoding="utf-8") as f:
        f.write("external edit")

    # ?force=true is ignored — still 409
    r2 = client.post(f"/api/v1/docs/{d['id']}/export-markdown?force=true")
    assert r2.status_code == 409

    # File remains unchanged
    with open(disk_path, encoding="utf-8") as f:
        assert f.read() == "external edit"


def test_export_doc_type_subfolder_spec(client: TestClient, tmp_path) -> None:
    _, pid = _seed_with_folder(client, tmp_path)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "My Spec", "doc_type": "spec"},
    ).json()
    client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "spec"},
    )
    r = client.post(f"/api/v1/docs/{d['id']}/export-markdown")
    assert r.status_code == 200
    assert r.json()["export_path"].startswith("docs/product/")


def test_export_doc_not_found(client: TestClient) -> None:
    res = client.post("/api/v1/docs/doc_missing/export-markdown")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Migration round-trip (integration)
# ---------------------------------------------------------------------------


def test_doc_table_exists(client: TestClient) -> None:
    """Smoke test: the doc table is reachable via the API."""
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/docs")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Hard delete
# ---------------------------------------------------------------------------


def test_delete_doc(client: TestClient) -> None:
    _, pid = _seed(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Gone", "doc_type": "note"},
    ).json()
    assert client.delete(f"/api/v1/docs/{d['id']}").status_code == 204
    assert client.get(f"/api/v1/docs/{d['id']}").status_code == 404


def test_delete_doc_not_found(client: TestClient) -> None:
    assert client.delete("/api/v1/docs/doc_missing").status_code == 404


def test_delete_doc_cascades_comments_and_promotes_children(client: TestClient) -> None:
    """Deleting a doc removes its doc-scoped comments/links and promotes child
    docs to top-level rather than deleting them."""
    _, pid = _seed(client)
    parent = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Canvas", "doc_type": "canvas", "editor_format": "excalidraw"},
    ).json()
    child = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "Child", "doc_type": "note", "parent_doc_id": parent["id"]},
    ).json()
    client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "doc", "entity_id": parent["id"], "body": "pin note"},
    )

    assert client.delete(f"/api/v1/docs/{parent['id']}").status_code == 204

    # Comment on the deleted doc is gone…
    remaining = client.get(
        f"/api/v1/projects/{pid}/comments",
        params={"entity_type": "doc", "entity_id": parent["id"]},
    ).json()
    assert remaining == []
    # …and the child survives, promoted to top-level.
    got = client.get(f"/api/v1/docs/{child['id']}")
    assert got.status_code == 200
    assert got.json()["parent_doc_id"] is None
