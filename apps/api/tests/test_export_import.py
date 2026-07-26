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
    task_b = _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Task B"})
    _create(client, f"/api/v1/projects/{proj}/decisions", {"title": "D1", "decision": "do it"})
    _create(client, f"/api/v1/projects/{proj}/comments", {"entity_type": "task", "entity_id": task["id"], "body": "hi"})
    _create(
        client,
        f"/api/v1/projects/{proj}/connections",
        {
            "relation_type": "depends_on",
            "source_entity_type": "task",
            "source_entity_id": task["id"],
            "target_entity_type": "task",
            "target_entity_id": task_b["id"],
        },
    )

    exported = client.get(f"/api/v1/projects/{proj}/export")
    assert exported.status_code == 200, exported.text
    data = exported.json()
    assert data["planarus_export"] == 3  # #87 added three entities; Phase 25 added connections
    assert len(data["tasks"]) == 2
    assert len(data["phases"]) == 1
    assert len(data["decisions"]) == 1
    assert len(data["comments"]) == 1
    assert len(data["connections"]) == 1

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
    assert len(copy["connections"]) == 1
    assert {t["id"] for t in copy["tasks"]}.isdisjoint({t["id"] for t in data["tasks"]})
    # task→phase FK remapped into the copy's own phase
    copy_phase_ids = {p["id"] for p in copy["phases"]}
    linked = [t for t in copy["tasks"] if t.get("phase_id")]
    assert len(linked) == 1
    assert linked[0]["phase_id"] in copy_phase_ids
    # comment→task polymorphic remap: entity_id points at a copy task
    assert copy["comments"][0]["entity_id"] in {t["id"] for t in copy["tasks"]}
    copy_task_ids = {t["id"] for t in copy["tasks"]}
    assert copy["connections"][0]["source_entity_id"] in copy_task_ids
    assert copy["connections"][0]["target_entity_id"] in copy_task_ids


def test_import_drops_a_connection_whose_endpoints_are_not_in_the_payload(client):
    """A forged endpoint must never reach the new project (#87 drop semantics).

    `copy_graph` resolves both endpoints through this copy's own id map and skips
    the row when either is missing — the same rule comments and links follow. The
    property under test is that the forged ids are not written through: an import
    that quietly attached the new project to `tsk_missing` would be the bug.
    """
    ws, proj = seed(client, "exp-connection-forge")
    data = client.get(f"/api/v1/projects/{proj}/export").json()
    data["connections"] = [
        {
            "id": "con_forged",
            "project_id": proj,
            "relation_type": "depends_on",
            "source_entity_type": "task",
            "source_entity_id": "tsk_missing",
            "target_entity_type": "task",
            "target_entity_id": "tsk_missing_2",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    response = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert response.status_code == 201, response.text
    copy = client.get(f"/api/v1/projects/{response.json()['id']}/export").json()
    assert copy["connections"] == []


def test_import_rejects_a_connection_the_relation_matrix_forbids(client):
    """`row_check` runs before the first row is written, so nothing is created."""
    ws, proj = seed(client, "exp-connection-illegal")
    data = client.get(f"/api/v1/projects/{proj}/export").json()
    data["connections"] = [
        {
            "id": "con_illegal",
            "project_id": proj,
            "relation_type": "mitigates",  # task -> risk only
            "source_entity_type": "doc",
            "source_entity_id": "doc_1",
            "target_entity_type": "doc",
            "target_entity_id": "doc_2",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    response = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert response.status_code == 422, response.text


def test_import_coerces_priority_to_the_allowed_scale(client):
    """#158 review: the column has no DB CHECK and ProjectImport does not cover
    `priority`, so import was the one write path that could land an arbitrary
    string in a field the Dashboard renders as a badge."""
    ws, proj = seed(client, "expprio")
    data = client.get(f"/api/v1/projects/{proj}/export").json()

    # A valid value survives the round trip.
    data["project"]["priority"] = "high"
    kept = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert kept.status_code == 201, kept.text
    assert kept.json()["priority"] == "high"

    # Anything outside the scale drops to None rather than reaching the column.
    for junk in ("P0 URGENT", "", "HIGH", 3, ["high"]):
        data["project"]["priority"] = junk
        res = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
        assert res.status_code == 201, res.text
        assert res.json()["priority"] is None, junk


def test_import_rejects_unrecognized_payload(client):
    ws, _ = seed(client, "expbad")
    res = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": {"nope": 1}})
    assert res.status_code == 422


def test_export_missing_project_404(client):
    res = client.get("/api/v1/projects/proj_does_not_exist/export")
    assert res.status_code == 404


def test_import_remaps_decision_and_risk_phase(client):
    """Phase 19: import_project has its own graph walk, separate from
    duplicate_project's — the phase_id remap must be applied here too, or the
    copy points at the SOURCE project's phase (and 500s on another instance)."""
    ws, proj = seed(client, "exp-phase")
    phase = _create(client, f"/api/v1/projects/{proj}/phases", {"title": "Phase 1"})
    _create(client, f"/api/v1/projects/{proj}/decisions",
            {"title": "D-phased", "decision": "x", "phase_id": phase["id"]})
    _create(client, f"/api/v1/projects/{proj}/risks",
            {"title": "R-phased", "severity": "high", "phase_id": phase["id"]})
    _create(client, f"/api/v1/projects/{proj}/decisions", {"title": "D-global", "decision": "y"})

    data = client.get(f"/api/v1/projects/{proj}/export").json()
    new = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert new.status_code in (200, 201), new.text
    new_id_ = new.json()["id"]

    new_phase_ids = {p["id"] for p in client.get(f"/api/v1/projects/{new_id_}/phases").json()}
    assert phase["id"] not in new_phase_ids  # remapped, so the source id is gone

    decisions = {d["title"]: d["phase_id"] for d in client.get(f"/api/v1/projects/{new_id_}/decisions").json()}
    risks = {r["title"]: r["phase_id"] for r in client.get(f"/api/v1/projects/{new_id_}/risks").json()}
    assert decisions["D-phased"] in new_phase_ids, "decision must point at the COPY's phase"
    assert risks["R-phased"] in new_phase_ids, "risk must point at the COPY's phase"
    assert decisions["D-global"] is None


def test_import_drops_unresolvable_phase_reference(client):
    """A caller-supplied phase_id that isn't in this import's own payload must
    become NULL, never be written through at a foreign project's row."""
    ws, proj = seed(client, "exp-forge")
    other_ws, other_proj = seed(client, "exp-victim")
    victim_phase = _create(client, f"/api/v1/projects/{other_proj}/phases", {"title": "Victim"})

    data = client.get(f"/api/v1/projects/{proj}/export").json()
    data["phases"] = []
    data["decisions"] = [{
        "id": "dec_forged", "project_id": proj, "phase_id": victim_phase["id"],
        "title": "forged", "decision": "x", "context": None, "status": "proposed",
        "sort_order": 0, "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }]

    new = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert new.status_code in (200, 201), new.text
    imported = client.get(f"/api/v1/projects/{new.json()['id']}/decisions").json()
    assert [d["phase_id"] for d in imported] == [None]
