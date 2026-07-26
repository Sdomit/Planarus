from app.models.audit_event import AuditEvent
from app.models.entity_connection import EntityConnection
from app.schemas.task import TaskCreate
from app.services import task_service
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _seed(client: TestClient, suffix: str = "con") -> str:
    workspace = client.post(
        "/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}
    ).json()
    project = client.post(
        "/api/v1/projects",
        json={"workspace_id": workspace["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return project["id"]


def _task(client: TestClient, project_id: str, title: str) -> dict:
    response = client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def _connection(client: TestClient, project_id: str, **data) -> dict:
    response = client.post(f"/api/v1/projects/{project_id}/connections", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_connection_from_both_endpoints(client: TestClient) -> None:
    project_id = _seed(client)
    first = _task(client, project_id, "Build")
    second = _task(client, project_id, "Ship")
    connection = _connection(
        client,
        project_id,
        relation_type="depends_on",
        source_entity_type="task",
        source_entity_id=first["id"],
        target_entity_type="task",
        target_entity_id=second["id"],
    )
    assert connection["id"].startswith("con_")

    for task in (first, second):
        listed = client.get(
            f"/api/v1/projects/{project_id}/connections",
            params={"entity_type": "task", "entity_id": task["id"]},
        )
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [connection["id"]]


def test_related_connection_is_canonical_and_cannot_duplicate(client: TestClient) -> None:
    project_id = _seed(client, "canonical")
    left = _task(client, project_id, "One")
    right = _task(client, project_id, "Two")
    first = _connection(
        client,
        project_id,
        relation_type="related_to",
        source_entity_type="task",
        source_entity_id=right["id"],
        target_entity_type="task",
        target_entity_id=left["id"],
    )
    assert (first["source_entity_type"], first["source_entity_id"]) < (
        first["target_entity_type"],
        first["target_entity_id"],
    )
    duplicate = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "related_to",
            "source_entity_type": "task",
            "source_entity_id": left["id"],
            "target_entity_type": "task",
            "target_entity_id": right["id"],
        },
    )
    assert duplicate.status_code == 422


def test_connection_rejects_cross_project_invalid_direction_and_cycle(client: TestClient) -> None:
    project_id = _seed(client, "rules")
    other_project_id = _seed(client, "other")
    first = _task(client, project_id, "One")
    second = _task(client, project_id, "Two")
    foreign = _task(client, other_project_id, "Foreign")

    invalid_direction = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "implements",
            "source_entity_type": "task",
            "source_entity_id": first["id"],
            "target_entity_type": "task",
            "target_entity_id": second["id"],
        },
    )
    assert invalid_direction.status_code == 422
    cross_project = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "depends_on",
            "source_entity_type": "task",
            "source_entity_id": first["id"],
            "target_entity_type": "task",
            "target_entity_id": foreign["id"],
        },
    )
    assert cross_project.status_code == 404

    _connection(
        client,
        project_id,
        relation_type="depends_on",
        source_entity_type="task",
        source_entity_id=first["id"],
        target_entity_type="task",
        target_entity_id=second["id"],
    )
    cycle = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "depends_on",
            "source_entity_type": "task",
            "source_entity_id": second["id"],
            "target_entity_type": "task",
            "target_entity_id": first["id"],
        },
    )
    assert cycle.status_code == 422


def test_task_delete_cleans_connections_and_direct_delete_audits(
    client: TestClient, session: Session
) -> None:
    project_id = _seed(client, "delete")
    first = _task(client, project_id, "One")
    second = _task(client, project_id, "Two")
    connection = _connection(
        client,
        project_id,
        relation_type="depends_on",
        source_entity_type="task",
        source_entity_id=first["id"],
        target_entity_type="task",
        target_entity_id=second["id"],
    )
    deleted = client.delete(f"/api/v1/entity-connections/{connection['id']}")
    assert deleted.status_code == 204
    assert session.get(EntityConnection, connection["id"]) is None
    audit = session.exec(
        select(AuditEvent).where(
            AuditEvent.entity_type == "entity_connection",
            AuditEvent.entity_id == connection["id"],
            AuditEvent.event_type == "delete",
        )
    ).one()
    assert audit.project_id == project_id

    _connection(
        client,
        project_id,
        relation_type="depends_on",
        source_entity_type="task",
        source_entity_id=first["id"],
        target_entity_type="task",
        target_entity_id=second["id"],
    )
    assert client.delete(f"/api/v1/tasks/{first['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{project_id}/connections").json() == []


def test_connection_requires_both_filter_fields(client: TestClient) -> None:
    project_id = _seed(client, "filter")
    response = client.get(
        f"/api/v1/projects/{project_id}/connections", params={"entity_type": "task"}
    )
    assert response.status_code == 422


def test_service_cycle_validation_covers_transitive_dependencies(
    client: TestClient, session: Session
) -> None:
    project_id = _seed(client, "transitive")
    one = task_service.create_task(session, project_id, TaskCreate(title="One"))
    two = task_service.create_task(session, project_id, TaskCreate(title="Two"))
    three = task_service.create_task(session, project_id, TaskCreate(title="Three"))
    for source, target in ((one, two), (two, three)):
        _connection(
            client,
            project_id,
            relation_type="depends_on",
            source_entity_type="task",
            source_entity_id=source.id,
            target_entity_type="task",
            target_entity_id=target.id,
        )
    response = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "depends_on",
            "source_entity_type": "task",
            "source_entity_id": three.id,
            "target_entity_type": "task",
            "target_entity_id": one.id,
        },
    )
    assert response.status_code == 422


# --- Phase and Document endpoints (plan 25's affordance table) ----------------
# The UI gained Phase and Document connection sections without touching the API.
# These pin the server side of that claim: the relation matrix already accepts
# both, so a UI regression cannot be excused as "the backend never allowed it",
# and a matrix change that drops them fails here rather than silently in a panel.


def _phase(client: TestClient, project_id: str, title: str) -> dict:
    response = client.post(f"/api/v1/projects/{project_id}/phases", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def _doc(client: TestClient, project_id: str, title: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/docs",
        json={"title": title, "doc_type": "spec"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_phase_references_doc_and_doc_lists_it_from_its_own_endpoint(
    client: TestClient,
) -> None:
    project_id = _seed(client, "conphase")
    phase = _phase(client, project_id, "Phase 2")
    doc = _doc(client, project_id, "Architecture")

    created = _connection(
        client,
        project_id,
        relation_type="references",
        source_entity_type="phase",
        source_entity_id=phase["id"],
        target_entity_type="doc",
        target_entity_id=doc["id"],
    )
    assert created["relation_type"] == "references"

    # Reachable from the document too — that is what makes the doc-side
    # "Referenced by" section possible without a second query shape.
    from_doc = client.get(
        f"/api/v1/projects/{project_id}/connections",
        params={"entity_type": "doc", "entity_id": doc["id"]},
    )
    assert from_doc.status_code == 200, from_doc.text
    assert [row["id"] for row in from_doc.json()] == [created["id"]]


def test_doc_cannot_be_the_source_of_references(client: TestClient) -> None:
    project_id = _seed(client, "condocsrc")
    phase = _phase(client, project_id, "Phase 2")
    doc = _doc(client, project_id, "Architecture")

    # `references` is directional: every pair in the matrix ends at a doc. The
    # doc-side composer therefore has to store the reverse form, and this is the
    # rejection that makes that a requirement rather than a stylistic choice.
    response = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "references",
            "source_entity_type": "doc",
            "source_entity_id": doc["id"],
            "target_entity_type": "phase",
            "target_entity_id": phase["id"],
        },
    )
    assert response.status_code == 422, response.text
    assert "references" in response.json()["detail"]


def test_phase_and_doc_accept_related_to_in_either_orientation(
    client: TestClient,
) -> None:
    project_id = _seed(client, "conrelated")
    phase = _phase(client, project_id, "Phase 2")
    doc = _doc(client, project_id, "Architecture")

    _connection(
        client,
        project_id,
        relation_type="related_to",
        source_entity_type="phase",
        source_entity_id=phase["id"],
        target_entity_type="doc",
        target_entity_id=doc["id"],
    )
    # Canonicalized, so proposing the mirror image is the same edge, not a second.
    duplicate = client.post(
        f"/api/v1/projects/{project_id}/connections",
        json={
            "relation_type": "related_to",
            "source_entity_type": "doc",
            "source_entity_id": doc["id"],
            "target_entity_type": "phase",
            "target_entity_id": phase["id"],
        },
    )
    assert duplicate.status_code == 422, duplicate.text


def test_phase_delete_removes_its_doc_reference(client: TestClient, session: Session) -> None:
    project_id = _seed(client, "conphasedel")
    phase = _phase(client, project_id, "Phase 2")
    doc = _doc(client, project_id, "Architecture")
    _connection(
        client,
        project_id,
        relation_type="references",
        source_entity_type="phase",
        source_entity_id=phase["id"],
        target_entity_type="doc",
        target_entity_id=doc["id"],
    )

    assert client.delete(f"/api/v1/phases/{phase['id']}").status_code == 204
    session.expunge_all()
    remaining = session.exec(
        select(EntityConnection).where(EntityConnection.project_id == project_id)
    ).all()
    assert remaining == []
