"""P17.6 — project export / import round-trip (JSON, id-remapped)."""
from tests.external_util import seed


def _create(client, path, body):
    res = client.post(path, json=body)
    assert res.status_code in (200, 201), f"{path}: {res.status_code} {res.text}"
    return res.json()


def test_project_export_import_round_trips(client):
    ws, proj = seed(client, "exp")
    phase = _create(client, f"/api/v1/projects/{proj}/phases", {"title": "Phase 1"})
    task = _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Task A", "phase_id": phase["id"]})
    _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Task B"})
    _create(client, f"/api/v1/projects/{proj}/decisions", {"title": "D1", "decision": "do it"})
    _create(client, f"/api/v1/projects/{proj}/comments", {"entity_type": "task", "entity_id": task["id"], "body": "hi"})

    exported = client.get(f"/api/v1/projects/{proj}/export")
    assert exported.status_code == 200, exported.text
    data = exported.json()
    assert data["approvo_export"] == 1
    assert len(data["tasks"]) == 2
    assert len(data["phases"]) == 1
    assert len(data["decisions"]) == 1
    assert len(data["comments"]) == 1

    res = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert res.status_code == 201, res.text
    new_proj = res.json()
    assert new_proj["id"] != proj

    # The copy's graph mirrors the original, with every id remapped.
    copy = client.get(f"/api/v1/projects/{new_proj['id']}/export").json()
    assert len(copy["tasks"]) == 2
    assert len(copy["phases"]) == 1
    assert len(copy["decisions"]) == 1
    assert len(copy["comments"]) == 1
    assert {t["id"] for t in copy["tasks"]}.isdisjoint({t["id"] for t in data["tasks"]})
    # task→phase FK remapped into the copy's own phase
    copy_phase_ids = {p["id"] for p in copy["phases"]}
    linked = [t for t in copy["tasks"] if t.get("phase_id")]
    assert len(linked) == 1
    assert linked[0]["phase_id"] in copy_phase_ids
    # comment→task polymorphic remap: entity_id points at a copy task
    assert copy["comments"][0]["entity_id"] in {t["id"] for t in copy["tasks"]}


def test_import_rejects_unrecognized_payload(client):
    ws, _ = seed(client, "expbad")
    res = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": {"nope": 1}})
    assert res.status_code == 422


def test_export_missing_project_404(client):
    res = client.get("/api/v1/projects/proj_does_not_exist/export")
    assert res.status_code == 404
