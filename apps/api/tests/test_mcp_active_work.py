"""#93: get_active_work as a usable entry point.

Two gaps this pins:

- Open blockers were invisible to every agent surface (`grep Blocker app/mcp/`
  returned zero hits). The one entity type whose entire purpose is "don't work on
  this yet" was the one an agent could not see.
- No tool listed phases, so the `phase_id` scalar on every task/decision/risk row
  was an unresolvable opaque token.
"""
from app.mcp import registry
from app.mcp.tools import read
from app.schemas.blocker import BlockerCreate
from app.schemas.phase import PhaseCreate
from app.services import blocker_service, phase_service
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.mcp_util import read_cap, seed


def test_open_blockers_are_visible(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "aw1")
    blocker_service.create_blocker(
        session, pid, BlockerCreate(title="Waiting on vendor key")
    )
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert res.metadata["open_blocker_count"] == 1
    assert "Waiting on vendor key" in res.text


def test_resolved_blockers_are_excluded(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "aw2")
    blocker_service.create_blocker(
        session, pid, BlockerCreate(title="Already sorted", status="resolved")
    )
    blocker_service.create_blocker(session, pid, BlockerCreate(title="Still stuck"))
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert res.metadata["open_blocker_count"] == 1
    assert "Still stuck" in res.text
    assert "Already sorted" not in res.text


def test_blockers_are_project_scoped(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "aw3")
    _, other = seed(client, "aw4")
    blocker_service.create_blocker(session, other, BlockerCreate(title="Foreign leak"))
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert res.metadata["open_blocker_count"] == 0
    assert "Foreign leak" not in res.text


def test_phase_roster_resolves_phase_ids(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "aw5")
    p1 = phase_service.create_phase(session, pid, PhaseCreate(title="Discovery"))
    p2 = phase_service.create_phase(session, pid, PhaseCreate(title="Delivery"))
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    # Ids ride in metadata (safe scalars); titles stay inside the wrapped block.
    # They must stay index-aligned, which is the whole resolution mechanism.
    assert res.metadata["phase_ids"] == [p1.id, p2.id]
    assert res.metadata["phase_count"] == 2
    assert "phase[0]: planned · Discovery" in res.text
    assert "phase[1]: planned · Delivery" in res.text


def test_phase_ids_are_not_emitted_into_block_text(
    client: TestClient, session: Session
) -> None:
    """Ids in text come back masked, so the roster must not rely on them."""
    ws, pid = seed(client, "aw8")
    phase = phase_service.create_phase(session, pid, PhaseCreate(title="Discovery"))
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert phase.id in res.metadata["phase_ids"]
    assert f"phase[0]: planned · {phase.id}" not in res.text


def test_phase_roster_absent_when_no_phases(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "aw6")
    cap = read_cap(ws, pid)
    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    assert res.metadata["phase_count"] == 0
    assert res.metadata["phase_ids"] == []
    assert "phase_roster" not in res.text


def test_titles_never_leak_into_metadata(client: TestClient, session: Session) -> None:
    """The module contract: metadata carries safe scalars only."""
    ws, pid = seed(client, "aw7")
    phase_service.create_phase(session, pid, PhaseCreate(title="SECRET_PHASE_TITLE"))
    blocker_service.create_blocker(
        session, pid, BlockerCreate(title="SECRET_BLOCKER_TITLE")
    )
    cap = read_cap(ws, pid)

    res = read.get_active_work(session, cap, read.ProjectArgs(project_id=pid))
    flat = repr(res.metadata)
    assert "SECRET_PHASE_TITLE" not in flat
    assert "SECRET_BLOCKER_TITLE" not in flat


def test_description_directs_agents_to_start_here() -> None:
    spec = registry.READ_TOOLS["get_active_work"]
    assert "START HERE" in spec.description
    # It must advertise what it already returns, so agents stop re-fetching it.
    for promised in ("blocker", "phase roster", "redundant"):
        assert promised in spec.description
