"""Bounded internal payloads (#117).

The external API had a streamed 64 KiB body cap; `/api/v1` had none, so a body
was buffered in full before anything looked at its size. `ProjectImport.data` was
an arbitrary dict that `import_project` iterated while creating rows, and
`markdown_cache` — `content_json`'s derived twin — was uncapped while
`content_json` was capped at 2 MiB.
"""
import json

import pytest
from app.api.external.middleware import LOCAL_MAX_BODY_BYTES
from app.models.project import Project
from app.services import export_service


@pytest.fixture(name="project")
def project_fixture(client):
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "wpb"}).json()["id"]
    return client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "pbp"}
    ).json()["id"]


def _doc(client, project_id):
    r = client.post(
        f"/api/v1/projects/{project_id}/docs", json={"title": "D", "doc_type": "note"}
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- the app-wide ceiling ---------------------------------------------------


def test_oversized_body_is_refused_with_413(client, project):
    """Declared Content-Length over the ceiling: refused, and the id travels."""
    r = client.post(
        f"/api/v1/projects/{project}/docs",
        content=b"x" * (LOCAL_MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413, r.text
    assert "limit" in r.json()["detail"]
    assert r.json()["request_id"].startswith("req_")
    assert r.headers.get("x-request-id")


def test_oversized_streamed_body_is_refused_without_a_content_length(client, project):
    """Chunked upload, no declared length — the actual byte count still stops it."""

    def chunks():
        for _ in range((LOCAL_MAX_BODY_BYTES // (256 * 1024)) + 2):
            yield b"x" * (256 * 1024)

    r = client.post(
        f"/api/v1/projects/{project}/docs",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413, r.text


def test_a_normal_document_save_is_unaffected(client, project):
    """The ceiling must sit above real editor traffic, not inside it."""
    doc = _doc(client, project)
    content = json.dumps(
        {"type": "doc", "content": [{"type": "paragraph"} for _ in range(5_000)]}
    )
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": content, "markdown_cache": "# hi"},
    )
    assert r.status_code == 200, r.text


def test_get_requests_are_not_body_capped(client, project):
    assert client.get(f"/api/v1/projects/{project}/docs").status_code == 200


# --- document field and shape limits ----------------------------------------


def test_markdown_cache_is_capped(client, project):
    doc = _doc(client, project)
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={
            "version": doc["version"],
            "content_json": '{"type":"doc"}',
            "markdown_cache": "x" * (2 * 1024 * 1024 + 10),
        },
    )
    assert r.status_code == 422, r.text
    assert "markdown_cache" in r.text


def test_deeply_nested_content_json_is_rejected(client, project):
    """Small in bytes, ruinous to anything that walks it recursively."""
    doc = _doc(client, project)
    payload = {"type": "doc"}
    node = payload
    for _ in range(400):
        child = {"type": "paragraph"}
        node["content"] = [child]
        node = child
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={
            "version": doc["version"],
            "content_json": json.dumps(payload),
            "markdown_cache": "",
        },
    )
    assert r.status_code == 422, r.text
    assert "nests deeper" in r.text


def test_ordinary_nesting_still_saves(client, project):
    doc = _doc(client, project)
    payload = {"type": "doc"}
    node = payload
    for _ in range(20):  # a deeply indented list, but a real one
        child = {"type": "listItem"}
        node["content"] = [child]
        node = child
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={
            "version": doc["version"],
            "content_json": json.dumps(payload),
            "markdown_cache": "",
        },
    )
    assert r.status_code == 200, r.text


# --- import bounds ----------------------------------------------------------


def _export(client, project_id):
    r = client.get(f"/api/v1/projects/{project_id}/export")
    assert r.status_code == 200, r.text
    return r.json()


def test_valid_export_still_imports(client, project):
    payload = _export(client, project)
    r = client.post(
        "/api/v1/projects/import",
        json={"workspace_id": payload["project"]["workspace_id"], "data": payload},
    )
    assert r.status_code in (200, 201), r.text


def test_too_many_rows_is_rejected_and_writes_nothing(client, project, session):
    payload = _export(client, project)
    payload["tasks"] = [
        {"id": f"t{i}", "project_id": "x", "title": "T"}
        for i in range(export_service.MAX_ROWS_PER_ENTITY + 1)
    ]
    before = len(session.exec(Project.__table__.select()).all())
    r = client.post(
        "/api/v1/projects/import",
        json={"workspace_id": payload["project"]["workspace_id"], "data": payload},
    )
    assert r.status_code in (400, 422), r.text
    session.expire_all()
    after = len(session.exec(Project.__table__.select()).all())
    assert after == before, "a rejected import created a partial project"


def test_deeply_nested_import_is_rejected(client, project):
    payload = _export(client, project)
    node = payload["project"]
    for _ in range(export_service.MAX_IMPORT_DEPTH + 5):
        node["nested"] = {}
        node = node["nested"]
    r = client.post(
        "/api/v1/projects/import",
        json={"workspace_id": payload["project"]["workspace_id"], "data": payload},
    )
    assert r.status_code in (400, 422), r.text


def test_an_oversized_field_is_rejected(session):
    payload = {
        "planarus_export": export_service.EXPORT_VERSION,
        "project": {"title": "P"},
        "tasks": [{"id": "t1", "title": "x" * (export_service.MAX_FIELD_BYTES + 1)}],
    }
    with pytest.raises(ValueError, match="field limit"):
        export_service.validate_import_payload(payload)


def test_a_collection_that_is_not_a_list_is_rejected():
    payload = {
        "planarus_export": export_service.EXPORT_VERSION,
        "project": {"title": "P"},
        "tasks": {"not": "a list"},
    }
    with pytest.raises(ValueError, match="must be a list"):
        export_service.validate_import_payload(payload)


def test_unrecognized_version_is_still_rejected():
    with pytest.raises(ValueError, match="unrecognized export format"):
        export_service.validate_import_payload({"planarus_export": 99})


# An entity with a `row_check` rejects a row that is merely well-bounded, so the
# bounds test needs one row per collection that its own check accepts. Add an
# entry here when you add a `row_check`; the failure names the collection.
_VALID_ROWS: dict[str, dict] = {
    "connections": {
        "id": "con_x",
        "relation_type": "depends_on",
        "source_entity_type": "task",
        "source_entity_id": "tsk_a",
        "target_entity_type": "task",
        "target_entity_id": "tsk_b",
    },
}


def _minimal_row(payload_key: str) -> dict:
    return _VALID_ROWS.get(payload_key, {"id": "x"})


def test_every_graph_entity_is_bounded():
    """The bounds are derived from project_graph, so a new entity cannot slip in
    unbounded — this pins that the derivation actually covers the registry."""
    from app.services import project_graph

    # copy_graph resolves the import surface to the export one, so this is the
    # exact set of collections an import reads.
    keys = {e.payload_key for e in project_graph.entities_for("export")}
    assert keys, "import surface is empty; the derivation would bound nothing"
    payload = {
        "planarus_export": export_service.EXPORT_VERSION,
        "project": {"title": "P"},
        **{k: [_minimal_row(k)] for k in keys},
    }
    export_service.validate_import_payload(payload)  # a valid one passes
    for key in keys:
        over = dict(payload)
        over[key] = [_minimal_row(key)] * (export_service.MAX_ROWS_PER_ENTITY + 1)
        with pytest.raises(ValueError, match="over the"):
            export_service.validate_import_payload(over)
