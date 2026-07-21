from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, slug: str = "test-ws") -> str:
    res = client.post("/api/v1/workspaces", json={"name": "Test WS", "slug": slug})
    assert res.status_code == 201
    return res.json()["id"]


def test_list_projects_empty(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_create_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    payload = {
        "workspace_id": ws_id,
        "title": "My Project",
        "slug": "my-project",
        "status": "planning",
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My Project"
    assert data["slug"] == "my-project"
    assert data["status"] == "planning"
    assert data["id"].startswith("proj_")
    assert data["workspace_id"] == ws_id
    assert "created_at" in data
    assert "updated_at" in data


def test_get_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    created = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Get Me", "slug": "get-me"},
    ).json()
    response = client.get(f"/api/v1/projects/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_project_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/projects/proj_doesnotexist")
    assert response.status_code == 404


def test_update_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    created = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Old Title", "slug": "old-title"},
    ).json()
    response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"title": "New Title", "status": "active"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["status"] == "active"


def test_update_project_not_found(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/projects/proj_doesnotexist",
        json={"title": "New"},
    )
    assert response.status_code == 404


def test_list_projects_by_workspace(client: TestClient) -> None:
    ws1 = _create_workspace(client, "workspace-one")
    ws2 = _create_workspace(client, "workspace-two")
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws1, "title": "P1", "slug": "p-one"},
    )
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2, "title": "P2", "slug": "p-two"},
    )
    res1 = client.get(f"/api/v1/projects?workspace_id={ws1}").json()
    res2 = client.get(f"/api/v1/projects?workspace_id={ws2}").json()
    assert len(res1) == 1 and res1[0]["slug"] == "p-one"
    assert len(res2) == 1 and res2[0]["slug"] == "p-two"


def test_create_project_invalid_status(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "X", "slug": "xx", "status": "invalid"},
    )
    assert response.status_code == 422


def test_create_project_invalid_slug(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "X", "slug": "-bad-"},
    )
    assert response.status_code == 422


def test_create_project_missing_workspace(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": "ws_nonexistent", "title": "X", "slug": "xx"},
    )
    assert response.status_code == 404


def test_create_project_duplicate_slug_conflict(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    first = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "First", "slug": "dup-proj"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Second", "slug": "dup-proj"},
    )
    assert second.status_code == 409
    assert "detail" in second.json()


def test_same_slug_allowed_in_different_workspaces(client: TestClient) -> None:
    ws1 = _create_workspace(client, "workspace-a")
    ws2 = _create_workspace(client, "workspace-b")
    r1 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws1, "title": "A", "slug": "shared-slug"},
    )
    r2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2, "title": "B", "slug": "shared-slug"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201


def test_audit_event_created_on_project_create(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    ws_id = _create_workspace(client)
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Audited", "slug": "audited"},
    )
    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "create")
    ).all()
    # workspace create + project create = 2 events
    project_events = [e for e in events if e.entity_type == "project"]
    assert len(project_events) == 1
    assert project_events[0].actor_type == "human"


def _create_project(client: TestClient, ws_id: str, slug: str = "p") -> str:
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "P", "slug": slug},
    ).json()["id"]


def test_archive_hides_from_default_list_and_unarchive_restores(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    pid = _create_project(client, ws_id, "arch-me")

    arch = client.post(f"/api/v1/projects/{pid}/archive")
    assert arch.status_code == 200
    assert arch.json()["status"] == "archived"
    assert arch.json()["archived_at"] is not None

    # Hidden by default, visible with include_archived.
    assert all(p["id"] != pid for p in client.get("/api/v1/projects").json())
    assert any(
        p["id"] == pid
        for p in client.get("/api/v1/projects?include_archived=true").json()
    )

    un = client.post(f"/api/v1/projects/{pid}/unarchive")
    assert un.status_code == 200
    assert un.json()["archived_at"] is None
    assert un.json()["status"] == "active"
    assert any(p["id"] == pid for p in client.get("/api/v1/projects").json())


def test_duplicate_deep_copies_children_with_remapped_ids(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    pid = _create_project(client, ws_id, "orig")
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "P1"}).json()
    task = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "T1", "phase_id": phase["id"]},
    ).json()
    client.post(f"/api/v1/tasks/{task['id']}/checklist-items", json={"label": "step"})
    client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "task", "entity_id": task["id"], "body": "note"},
    )

    dup = client.post(f"/api/v1/projects/{pid}/duplicate")
    assert dup.status_code == 201
    new = dup.json()
    assert new["id"] != pid
    assert new["title"] == "P (copy)"
    assert new["slug"] == "orig-copy"
    assert new["status"] == "idea"

    new_tasks = client.get(f"/api/v1/projects/{new['id']}/tasks").json()
    assert len(new_tasks) == 1
    assert new_tasks[0]["id"] != task["id"]  # remapped

    new_phases = client.get(f"/api/v1/projects/{new['id']}/phases").json()
    assert new_tasks[0]["phase_id"] == new_phases[0]["id"]  # internal FK remapped

    new_chk = client.get(
        f"/api/v1/tasks/{new_tasks[0]['id']}/checklist-items"
    ).json()
    assert len(new_chk) == 1

    new_comments = client.get(f"/api/v1/projects/{new['id']}/comments").json()
    assert len(new_comments) == 1
    # Polymorphic entity_id points at the COPIED task, not the source task.
    assert new_comments[0]["entity_id"] == new_tasks[0]["id"]


def test_delete_requires_archive_first(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    pid = _create_project(client, ws_id, "live")
    res = client.delete(f"/api/v1/projects/{pid}")
    assert res.status_code == 409
    assert client.get(f"/api/v1/projects/{pid}").status_code == 200  # still there


def test_delete_purges_archived_project_and_children(client: TestClient, session) -> None:
    from app.models.task import Task
    from sqlmodel import select

    ws_id = _create_workspace(client)
    pid = _create_project(client, ws_id, "doomed")
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"})

    client.post(f"/api/v1/projects/{pid}/archive")
    res = client.delete(f"/api/v1/projects/{pid}")
    assert res.status_code == 204
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    remaining = session.exec(select(Task).where(Task.project_id == pid)).all()
    assert remaining == []


def test_delete_missing_project_404(client: TestClient) -> None:
    assert client.delete("/api/v1/projects/proj_nope").status_code == 404


def test_audit_event_created_on_project_update(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    ws_id = _create_workspace(client)
    created = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Before", "slug": "to-update"},
    ).json()
    client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"status": "active"},
    )
    events = session.exec(
        select(AuditEvent).where(
            AuditEvent.event_type == "update",
            AuditEvent.entity_type == "project",
        )
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == created["id"]
    assert events[0].payload_json is not None
    assert "active" in events[0].payload_json


def test_duplicate_remaps_decision_and_risk_phase(client: TestClient) -> None:
    """Phase 19 (D45): the new phase_id FK must be remapped on copy, never left
    pointing at the source project's phase."""
    ws_id = _create_workspace(client)
    pid = _create_project(client, ws_id, "orig-graph")
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "P1"}).json()
    client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "X", "phase_id": phase["id"]},
    )
    client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "R", "severity": "high", "phase_id": phase["id"]},
    )
    # An unphased pair must survive as unphased.
    client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "D2", "decision": "Y"})
    client.post(f"/api/v1/projects/{pid}/risks", json={"title": "R2", "severity": "low"})

    new = client.post(f"/api/v1/projects/{pid}/duplicate").json()
    new_phase_id = client.get(f"/api/v1/projects/{new['id']}/phases").json()[0]["id"]
    assert new_phase_id != phase["id"]

    new_decisions = client.get(f"/api/v1/projects/{new['id']}/decisions").json()
    new_risks = client.get(f"/api/v1/projects/{new['id']}/risks").json()
    dec_phases = {d["title"]: d["phase_id"] for d in new_decisions}
    risk_phases = {r["title"]: r["phase_id"] for r in new_risks}

    assert dec_phases == {"D": new_phase_id, "D2": None}
    assert risk_phases == {"R": new_phase_id, "R2": None}
