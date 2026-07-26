"""#103: the tables that grow forever, and the queries that scale with them.

Each test here pins a *cost* claim, not just behaviour — a behavioural test would
pass equally well against the O(n) version it replaces. Query counting via a
`before_cursor_execute` hook is how the N+1 and the deferred column are proven.
"""
import pytest
from app.core.config import settings
from app.models.approval_request import ApprovalRequest
from app.services import approval_service
from app.services.auth_service import SESSION_COOKIE
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select


class QueryCounter:
    """Count SQL statements issued on an engine, optionally matching a substring."""

    def __init__(self, engine, contains: str | None = None) -> None:
        self.engine, self.contains, self.statements = engine, contains, []

    def __enter__(self):
        @event.listens_for(self.engine, "before_cursor_execute")
        def _record(conn, cursor, statement, params, context, executemany):
            if self.contains is None or self.contains in statement:
                self.statements.append(statement)

        self._handler = _record
        return self

    def __exit__(self, *exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._handler)

    def __len__(self) -> int:
        return len(self.statements)


def _seed_project(client: TestClient, suffix: str) -> tuple[str, str]:
    ws = client.post(
        "/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}
    ).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return ws["id"], proj["id"]


def _make_approvals(session: Session, ws: str, pid: str, n: int) -> None:
    for i in range(n):
        approval_service.create_proposal(
            session,
            project_id=pid,
            origin="mcp",
            actor_ref=f"agent-{i}",
            action_type="task.create",
            patch={"title": f"proposed task {i}", "description": "x" * 500},
        )


# --- approvals: bounded, and without dragging every patch body through Python --


def test_approvals_list_is_bounded_and_pages(client: TestClient, session: Session) -> None:
    ws, pid = _seed_project(client, "gr1")
    _make_approvals(session, ws, pid, 5)

    first = client.get(f"/api/v1/approvals?project_id={pid}&limit=2")
    assert first.status_code == 200
    assert len(first.json()) == 2
    assert first.headers["X-Total-Count"] == "5"
    assert first.headers["X-Has-More"] == "true"

    last = client.get(f"/api/v1/approvals?project_id={pid}&limit=2&offset=4")
    assert len(last.json()) == 1
    assert last.headers["X-Has-More"] == "false"


def test_approvals_pages_are_disjoint(client: TestClient, session: Session) -> None:
    ws, pid = _seed_project(client, "gr2")
    _make_approvals(session, ws, pid, 6)

    seen: list[str] = []
    for offset in (0, 2, 4):
        page = client.get(
            f"/api/v1/approvals?project_id={pid}&limit=2&offset={offset}"
        ).json()
        seen += [row["id"] for row in page]
    assert len(seen) == 6
    assert len(set(seen)) == 6, "paging served a row twice"


def test_approvals_list_does_not_load_patch_bodies(
    client: TestClient, session: Session, engine
) -> None:
    """The whole point of the deferred column: ApprovalSummary has no patch field,
    so loading it was pure waste on every queue render."""
    ws, pid = _seed_project(client, "gr3")
    _make_approvals(session, ws, pid, 3)

    with QueryCounter(engine, contains="proposed_patch_json") as counter:
        res = client.get(f"/api/v1/approvals?project_id={pid}")
    assert res.status_code == 200
    assert len(res.json()) == 3
    assert len(counter) == 0, f"patch body was selected: {counter.statements}"


def test_approval_detail_still_returns_the_patch(
    client: TestClient, session: Session
) -> None:
    """Deferring must not break the path that genuinely needs the body."""
    ws, pid = _seed_project(client, "gr4")
    _make_approvals(session, ws, pid, 1)
    approval_id = client.get(f"/api/v1/approvals?project_id={pid}").json()[0]["id"]

    detail = client.get(f"/api/v1/approvals/{approval_id}")
    assert detail.status_code == 200
    assert detail.json()["diff"], "detail must still build a diff from the patch"


def test_deferred_row_can_still_read_the_patch_attribute(
    client: TestClient, session: Session
) -> None:
    """A deferred column is lazy, not absent — the apply path must keep working."""
    ws, pid = _seed_project(client, "gr5")
    _make_approvals(session, ws, pid, 1)

    row = approval_service.list_approvals(session, project_id=pid)[0]
    assert "proposed task 0" in row.proposed_patch_json


def test_approvals_limit_is_capped(client: TestClient) -> None:
    _, pid = _seed_project(client, "gr6")
    assert client.get(f"/api/v1/approvals?project_id={pid}&limit=99999").status_code == 422
    assert client.get(f"/api/v1/approvals?project_id={pid}&offset=-1").status_code == 422


def test_default_status_filter_is_unchanged(
    client: TestClient, session: Session
) -> None:
    """The queue UI splits one unfiltered response into pending + history, so an
    implicit status=pending default would silently empty the history view."""
    ws, pid = _seed_project(client, "gr7")
    _make_approvals(session, ws, pid, 2)
    rows = session.exec(select(ApprovalRequest)).all()
    for row in rows:
        row.status = "rejected"
        session.add(row)
    session.commit()

    unfiltered = client.get(f"/api/v1/approvals?project_id={pid}").json()
    assert len(unfiltered) == 2, "non-pending rows must still be returned by default"


# --- status options: COUNT instead of materializing rows ----------------------


def test_status_option_delete_still_refuses_when_in_use(client: TestClient) -> None:
    _, pid = _seed_project(client, "gr8")
    opt = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "In review"},
    ).json()
    client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "t", "status": opt["key"]}
    )

    blocked = client.delete(f"/api/v1/status-options/{opt['id']}")
    assert blocked.status_code == 409


def test_status_option_delete_succeeds_when_unused(client: TestClient) -> None:
    _, pid = _seed_project(client, "gr9")
    opt = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "Unused"},
    ).json()
    assert client.delete(f"/api/v1/status-options/{opt['id']}").status_code == 204


def test_usage_count_does_not_select_full_rows(client: TestClient, engine) -> None:
    """It exists only to refuse a delete; the rows were always discarded."""
    _, pid = _seed_project(client, "gr10")
    opt = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "Counted"},
    ).json()
    for i in range(5):
        client.post(
            f"/api/v1/projects/{pid}/tasks",
            json={"title": f"t{i}", "status": opt["key"]},
        )

    with QueryCounter(engine, contains="count(") as counter:
        client.delete(f"/api/v1/status-options/{opt['id']}")
    assert len(counter) >= 1, "delete should COUNT, not materialize rows"


# --- workspace members: one IN query, not one per member ----------------------


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _login(client: TestClient, email: str) -> str:
    res = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert res.status_code == 200, res.text
    return client.cookies.get(SESSION_COOKIE)


def test_member_roster_is_batch_resolved(
    client: TestClient, session: Session, engine, auth_on
) -> None:
    owner = _login(client, "owner@example.com")
    ws = client.post(
        "/api/v1/workspaces",
        json={"name": "Acme", "slug": "acme-gr"},
        cookies={SESSION_COOKIE: owner},
    ).json()["id"]

    for i in range(4):
        email = f"member{i}@example.com"
        client.cookies.clear()
        _login(client, email)
        client.cookies.clear()
        added = client.post(
            f"/api/v1/workspaces/{ws}/members",
            json={"email": email, "role": "viewer"},
            cookies={SESSION_COOKIE: owner},
        )
        assert added.status_code == 201, added.text

    client.cookies.clear()
    # The test client shares this session, so every User created above is already
    # in the identity map and `session.get` would be a cache hit — which would
    # make this assertion pass against the N+1 it is meant to catch. Expunge so
    # the roster read has to reach the database.
    session.expunge_all()
    with QueryCounter(engine, contains="FROM appuser") as counter:
        res = client.get(
            f"/api/v1/workspaces/{ws}/members", cookies={SESSION_COOKIE: owner}
        )
    assert res.status_code == 200
    roster = res.json()
    assert len(roster) == 5  # owner + 4 viewers
    assert {m["email"] for m in roster} >= {"member0@example.com", "owner@example.com"}
    # Measured: 6 appuser SELECTs before the fix (one per member plus auth), 3
    # after (2 auth + 1 batch). One query resolves the whole roster; the auth
    # dependency adds its own
    # lookup for the caller, so allow a small constant but never one-per-member.
    assert len(counter) <= 3, f"N+1 on the roster: {len(counter)} user queries"


def test_actionable_statuses_can_be_fetched_as_a_set(
    client: TestClient, session: Session
) -> None:
    """#154 review: an old still-actionable proposal must stay reachable.

    Ordered by creation time, a pending row falls off a capped page once enough
    decided history piles up in front of it — and the queue panel is the only
    place it can be approved, rejected or applied. The panel therefore fetches
    pending/approved/applying by status rather than slicing them out of a page,
    which needs the filter to accept a set.
    """
    ws, pid = _seed_project(client, "gr14")
    _make_approvals(session, ws, pid, 5)
    rows = session.exec(select(ApprovalRequest)).all()
    # The oldest stays actionable; everything newer is decided history.
    for row in sorted(rows, key=lambda r: r.created_at)[1:]:
        row.status = "rejected"
        session.add(row)
    session.commit()

    # A single decided row is enough to push the pending one off this page.
    page = client.get(f"/api/v1/approvals?project_id={pid}&limit=1").json()
    assert all(r["status"] != "pending" for r in page), "precondition: pending is off-page"

    open_set = client.get(
        f"/api/v1/approvals?project_id={pid}&status=pending,approved,applying"
    )
    assert open_set.status_code == 200
    statuses = [r["status"] for r in open_set.json()]
    assert statuses == ["pending"], "the actionable row must still be reachable"


def test_single_status_filter_still_works(client: TestClient, session: Session) -> None:
    """The comma form is additive — one value must behave exactly as before."""
    ws, pid = _seed_project(client, "gr15")
    _make_approvals(session, ws, pid, 2)
    rows = session.exec(select(ApprovalRequest)).all()
    rows[0].status = "rejected"
    session.add(rows[0])
    session.commit()

    only_pending = client.get(f"/api/v1/approvals?project_id={pid}&status=pending").json()
    assert [r["status"] for r in only_pending] == ["pending"]


# --- notification feed: batched, not one query set per project ----------------


def _seed_feed_project(client: TestClient, suffix: str) -> str:
    """A project carrying one of each feed source: overdue task and open blocker."""
    _, pid = _seed_project(client, suffix)
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": f"late {suffix}", "due_at": "2000-01-01T00:00:00+00:00"},
    )
    client.post(
        f"/api/v1/projects/{pid}/blockers", json={"title": f"blocked {suffix}"}
    )
    return pid


def test_feed_query_count_does_not_scale_with_projects(
    client: TestClient, engine
) -> None:
    """The bell polls this forever in the background. Before: 4 queries per
    unarchived project. After: a fixed set of IN-queries for the whole feed."""
    for i in range(6):
        _seed_feed_project(client, f"nf{i}")

    with QueryCounter(engine, contains="FROM task") as tasks:
        with QueryCounter(engine, contains="FROM blocker") as blockers:
            with QueryCounter(engine, contains="FROM status_option") as statuses:
                res = client.get("/api/v1/notifications")
    assert res.status_code == 200
    # One batched query each, regardless of how many projects exist.
    assert len(tasks) == 1, f"task query per project: {len(tasks)}"
    assert len(blockers) == 1, f"blocker query per project: {len(blockers)}"
    assert len(statuses) == 1, f"status query per project: {len(statuses)}"


def test_feed_still_reports_every_project(client: TestClient) -> None:
    """Batching must not drop a project — the whole point of the global feed is
    that work in a project you are not looking at still reaches you."""
    ids = [_seed_feed_project(client, f"nb{i}") for i in range(3)]
    feed = client.get("/api/v1/notifications").json()
    reported = {item["project_id"] for item in feed["items"]}
    assert reported == set(ids)
    kinds = {item["kind"] for item in feed["items"]}
    assert {"task_overdue", "blocker_open"} <= kinds


def test_feed_closed_statuses_stay_per_project(client: TestClient) -> None:
    """The closed-status set is per project — a key marked done in one project
    must not silence the same key in another, which is exactly what a single
    shared WHERE would do."""
    _, quiet = _seed_project(client, "nq1")
    _, loud = _seed_project(client, "nq2")
    for pid in (quiet, loud):
        client.post(
            f"/api/v1/projects/{pid}/status-options",
            json={"entity_type": "task", "label": "Shipped", "key": "shipped"},
        )
    # Same key, opposite categories.
    shipped_quiet = client.get(
        f"/api/v1/projects/{quiet}/status-options?entity_type=task"
    ).json()
    opt = next(o for o in shipped_quiet if o["key"] == "shipped")
    client.patch(f"/api/v1/status-options/{opt['id']}", json={"category": "done"})

    for pid in (quiet, loud):
        client.post(
            f"/api/v1/projects/{pid}/tasks",
            json={"title": "overdue", "status": "shipped",
                  "due_at": "2000-01-01T00:00:00+00:00"},
        )

    overdue = {
        item["project_id"]
        for item in client.get("/api/v1/notifications").json()["items"]
        if item["kind"] == "task_overdue"
    }
    assert loud in overdue, "an open custom status must still nag"
    assert quiet not in overdue, "a done-category status must not nag"


# --- calendar: the date window is a WHERE, not a Python filter ----------------


def test_calendar_window_is_applied_in_sql(client: TestClient, engine) -> None:
    _, pid = _seed_project(client, "cal1")
    for day in ("2026-01-05", "2026-06-05", "2026-12-05"):
        client.post(
            f"/api/v1/projects/{pid}/tasks", json={"title": day, "due_at": day}
        )

    with QueryCounter(engine, contains="substr") as counter:
        res = client.get(
            f"/api/v1/projects/{pid}/calendar?from=2026-06-01&to=2026-06-30"
        )
    assert res.status_code == 200
    assert len(counter) >= 1, "the window never reached SQL"
    titles = [i["title"] for i in res.json()["items"]]
    assert titles == ["2026-06-05"]


def test_calendar_unwindowed_still_returns_everything(client: TestClient) -> None:
    """No bounds must mean no filter — the SQL clauses are conditional."""
    _, pid = _seed_project(client, "cal2")
    for day in ("2026-01-05", "2026-12-05"):
        client.post(
            f"/api/v1/projects/{pid}/tasks", json={"title": day, "due_at": day}
        )
    items = client.get(f"/api/v1/projects/{pid}/calendar").json()["items"]
    assert {i["title"] for i in items} == {"2026-01-05", "2026-12-05"}


def test_calendar_keeps_recurring_events_from_before_the_window(
    client: TestClient,
) -> None:
    """Events are deliberately *not* narrowed in SQL: a recurring event whose base
    date precedes the window still has occurrences inside it."""
    _, pid = _seed_project(client, "cal3")
    created = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={
            "title": "standup",
            "start_at": "2026-01-05",
            "all_day": True,
            "recurrence": "weekly",
        },
    )
    assert created.status_code == 201, created.text
    items = client.get(
        f"/api/v1/projects/{pid}/calendar?from=2026-06-01&to=2026-06-30"
    ).json()["items"]
    assert items, "a recurring event from before the window was dropped"


# --- reorder: write only what moved, and stop re-listing the table ------------


def test_reorder_writes_only_the_rows_that_moved(client: TestClient, engine) -> None:
    """A drag used to renumber every row of the type; on a 200-task board that was
    ~200 UPDATEs to move one card."""
    _, pid = _seed_project(client, "ro1")
    ids = [
        client.post(f"/api/v1/projects/{pid}/tasks", json={"title": f"t{i}"}).json()["id"]
        for i in range(6)
    ]
    # Swap the last two only.
    reordered = ids[:4] + [ids[5], ids[4]]

    with QueryCounter(engine, contains="UPDATE task") as counter:
        res = client.post(f"/api/v1/projects/{pid}/tasks/reorder", json={"ids": reordered})
    assert res.status_code == 200
    assert 0 < len(counter) <= 2, f"renumbered untouched rows: {len(counter)} UPDATEs"


def test_reorder_returns_what_a_fresh_list_would(client: TestClient) -> None:
    """The response is built from rows already in memory instead of a second full
    scan, so it has to match the re-query it replaced exactly."""
    _, pid = _seed_project(client, "ro2")
    ids = [
        client.post(f"/api/v1/projects/{pid}/tasks", json={"title": f"t{i}"}).json()["id"]
        for i in range(5)
    ]
    reordered = list(reversed(ids))

    returned = [t["id"] for t in client.post(
        f"/api/v1/projects/{pid}/tasks/reorder", json={"ids": reordered}
    ).json()]
    listed = [t["id"] for t in client.get(f"/api/v1/projects/{pid}/tasks").json()]
    assert returned == reordered
    assert returned == listed


def test_reorder_is_idempotent(client: TestClient, engine) -> None:
    """Re-sending the order already in force must write nothing at all."""
    _, pid = _seed_project(client, "ro3")
    ids = [
        client.post(f"/api/v1/projects/{pid}/tasks", json={"title": f"t{i}"}).json()["id"]
        for i in range(4)
    ]
    client.post(f"/api/v1/projects/{pid}/tasks/reorder", json={"ids": ids})

    with QueryCounter(engine, contains="UPDATE task") as counter:
        again = client.post(f"/api/v1/projects/{pid}/tasks/reorder", json={"ids": ids})
    assert again.status_code == 200
    assert len(counter) == 0, "a no-op reorder still wrote rows"
