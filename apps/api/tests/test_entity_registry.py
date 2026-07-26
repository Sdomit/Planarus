"""#94: the referenceable-entity registry and the two maps derived from it.

Before the registry, `entity_ref._REF_MODELS` and `timeline_service._RESOLVERS`
were hand-maintained restatements of REF_ENTITY_TYPES and both had drifted:
attaching to a `calendar_event` 404'd on a bare KeyError, and audited `milestone`
/ `calendar_event` timeline rows rendered with no title.

The structural tests below are the drift guard; the behavioural ones pin the
user-visible symptoms that drift produced.
"""
from app.core.constants import REF_ENTITY_TYPES
from app.services.entity_ref import _REF_MODELS
from app.services.entity_registry import ENTITY_MODELS
from app.services.timeline_service import _RESOLVERS
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-reg"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-reg"},
    ).json()
    return ws["id"], proj["id"]


# --- structural: the drift guards -------------------------------------------


def test_registry_covers_exactly_the_advertised_types() -> None:
    assert set(ENTITY_MODELS) == set(REF_ENTITY_TYPES)


def test_every_advertised_type_is_resolvable_as_a_reference() -> None:
    # "project" is scope-checked against the project id, not looked up by model.
    assert set(_REF_MODELS) == set(REF_ENTITY_TYPES) - {"project"}


def test_every_advertised_type_resolves_a_timeline_title() -> None:
    assert set(REF_ENTITY_TYPES) <= set(_RESOLVERS)


def test_registry_label_attributes_exist_on_their_models() -> None:
    for entity_type, (model, attr) in ENTITY_MODELS.items():
        assert hasattr(model, attr), f"{entity_type} -> {model.__name__}.{attr}"


# --- behavioural: what the drift actually broke ------------------------------


def _make_calendar_event(client: TestClient, pid: str) -> str:
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Design review", "start_at": "2026-08-03T09:00:00+00:00"},
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_comment_on_calendar_event_is_accepted(client: TestClient) -> None:
    _, pid = _seed(client)
    ev_id = _make_calendar_event(client, pid)

    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={
            "entity_type": "calendar_event",
            "entity_id": ev_id,
            "body": "Moved from Tuesday",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["entity_type"] == "calendar_event"


def test_link_on_calendar_event_is_accepted(client: TestClient) -> None:
    _, pid = _seed(client)
    ev_id = _make_calendar_event(client, pid)

    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={
            "entity_type": "calendar_event",
            "entity_id": ev_id,
            "url": "https://example.com/agenda",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["entity_type"] == "calendar_event"


def test_calendar_event_reference_is_still_scope_checked(client: TestClient) -> None:
    """Resolvable must not mean unchecked: a foreign event still 404s."""
    _, pid = _seed(client)
    other_ws = client.post(
        "/api/v1/workspaces", json={"name": "W2", "slug": "ws-reg2"}
    ).json()
    other_proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": other_ws["id"], "title": "P2", "slug": "p-reg2"},
    ).json()
    foreign_ev = _make_calendar_event(client, other_proj["id"])

    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "calendar_event", "entity_id": foreign_ev, "body": "x"},
    )
    assert res.status_code == 404


def test_timeline_resolves_milestone_title(client: TestClient) -> None:
    _, pid = _seed(client)
    created = client.post(
        f"/api/v1/projects/{pid}/milestones", json={"title": "Beta cutoff"}
    )
    assert created.status_code == 201

    events = client.get(f"/api/v1/projects/{pid}/timeline").json()["events"]
    rows = [e for e in events if e["entity_type"] == "milestone"]
    assert rows, "milestone create should be audited onto the timeline"
    # Unresolved rows degrade to a bare "create milestone" with no title suffix.
    assert rows[0]["label"].endswith("— Beta cutoff"), rows[0]["label"]


def test_timeline_resolves_calendar_event_title(client: TestClient) -> None:
    _, pid = _seed(client)
    _make_calendar_event(client, pid)

    events = client.get(f"/api/v1/projects/{pid}/timeline").json()["events"]
    rows = [e for e in events if e["entity_type"] == "calendar_event"]
    assert rows, "calendar_event create should be audited onto the timeline"
    assert rows[0]["label"].endswith("— Design review"), rows[0]["label"]
