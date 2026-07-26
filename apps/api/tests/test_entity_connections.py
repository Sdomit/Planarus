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
