"""Registry-completeness gate for ``tenant_guard`` (P0 follow-on to P10.2b).

``tenant_guard`` resolves the owning project from whichever identifier a route
carries and **returns silently** when it recognises none of them. That makes the
resolver registry in ``app.core.tenant`` load-bearing: a flat-item route whose
path param was never registered is not merely under-tested, it is *unguarded* —
no membership check and no role check for any caller holding a valid session.

Four routes shipped that way (comments, calendar events, status options,
calendar connections), all reachable in LAN team mode, where a viewer could
mutate them. ``test_every_guarded_route_resolves_a_tenant`` fails CI on the next
one instead of waiting for a review to notice.
"""
from datetime import datetime, timezone

import pytest
from app.core.config import settings
from app.core.tenant import _build_resolvers, tenant_guard
from app.main import app
from app.services.auth_service import SESSION_COOKIE

# Routes under the guard that legitimately resolve no tenant. Each needs a reason:
# the point of the allowlist is to make "unguarded" a decision someone wrote down.
GLOBAL_ROUTES = {
    ("GET", "/api/v1/calendar-sync/providers"): "static provider list, no tenant data",
    ("GET", "/api/v1/context-pack/profiles"): "static built-in profiles, no tenant data",
    ("GET", "/api/v1/calendar-sync/{provider}/callback"): (
        "OAuth callback — authorized by the signed state (which carries project_id); "
        "the URL holds no tenant identifier to resolve"
    ),
}


def _route_contexts():
    """Every route in the app, with router-level dependencies merged in.

    FastAPI >=0.13x keeps included routers as ``_IncludedRouter`` nodes rather
    than flattening them, so walking ``app.routes`` directly finds only
    ``/health`` and this whole module would pass vacuously. The route counts
    asserted below exist to catch exactly that if the traversal ever breaks.
    """
    for route in app.routes:
        expand = getattr(route, "effective_route_contexts", None)
        if expand is not None:
            yield from expand()


def _is_guarded(ctx) -> bool:
    seen, stack = set(), [ctx.dependant]
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        if getattr(dep, "call", None) is tenant_guard:
            return True
        stack.extend(dep.dependencies)
    return False


def test_every_guarded_route_resolves_a_tenant():
    contexts = [c for c in _route_contexts() if c.path.startswith("/api/v1")]
    assert len(contexts) > 100, "route traversal broke; this test would pass vacuously"
    guarded = [c for c in contexts if _is_guarded(c)]
    assert len(guarded) > 50, "no routes seen as guarded; traversal or guard changed"

    resolvers = set(_build_resolvers())
    unresolved = []
    for ctx in guarded:
        params = set(getattr(ctx, "param_convertors", {}) or {})
        if params & resolvers:
            continue
        if any(p.name == "project_id" for p in ctx.dependant.query_params):
            continue
        for method in sorted(set(ctx.methods) - {"HEAD", "OPTIONS"}):
            if (method, ctx.path) not in GLOBAL_ROUTES:
                unresolved.append(f"{method} {ctx.path}  params={sorted(params) or '[]'}")

    assert not unresolved, (
        "These routes are under tenant_guard but carry no identifier it can resolve, "
        "so the guard returns without checking workspace membership OR role:\n  "
        + "\n  ".join(sorted(unresolved))
        + "\n\nFix: add a resolver for the path param to _build_resolvers() in "
        "app/core/tenant.py. If the route is genuinely global, add it to "
        "GLOBAL_ROUTES here with a reason."
    )


def test_global_route_allowlist_has_no_stale_entries():
    """An exemption for a route that no longer exists is a blanket, not a decision."""
    live = {
        (method, ctx.path)
        for ctx in _route_contexts()
        for method in set(ctx.methods) - {"HEAD", "OPTIONS"}
    }
    assert not (set(GLOBAL_ROUTES) - live), (
        f"GLOBAL_ROUTES exempts routes that no longer exist: "
        f"{sorted(set(GLOBAL_ROUTES) - live)}"
    )


def _seed(session, project_id):
    """One row per newly-registered resolver, created straight through the services."""
    from app.models.calendar_connection import CalendarConnection
    from app.schemas.calendar_event import CalendarEventCreate
    from app.schemas.comment import CommentCreate
    from app.schemas.status_option import StatusOptionCreate
    from app.services import calendar_event_service, comment_service, status_option_service

    now = datetime.now(timezone.utc).isoformat()
    conn = CalendarConnection(
        id=f"conn-{project_id}",
        project_id=project_id,
        provider="google",
        account_email="cal@acme.co",
        access_token_enc="not-a-real-token",
        created_at=now,
        updated_at=now,
    )
    session.add(conn)
    session.commit()
    return {
        "comment_id": comment_service.create_comment(
            session,
            project_id,
            CommentCreate(entity_type="project", entity_id=project_id, body="hi"),
        ).id,
        "event_id": calendar_event_service.create_calendar_event(
            session, project_id, CalendarEventCreate(title="E", start_at="2026-07-20T10:00:00Z")
        ).id,
        "option_id": status_option_service.create_status_option(
            session, project_id, StatusOptionCreate(entity_type="task", label="Percolating")
        ).id,
        "connection_id": conn.id,
    }


def test_new_resolvers_return_the_owning_project(session):
    """Guards against a resolver wired to the wrong model — which would resolve
    None, 404 the legitimate owner, and look like a broken feature, not a leak."""
    from app.models.project import Project
    from app.models.workspace import Workspace

    now = datetime.now(timezone.utc).isoformat()
    session.add(Workspace(id="ws-res", name="W", slug="wres", created_at=now, updated_at=now))
    session.commit()  # FK target must exist first — no relationship() to order it
    session.add(
        Project(
            id="proj-res",
            workspace_id="ws-res",
            title="P",
            slug="pres",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()

    ids = _seed(session, "proj-res")
    resolvers = _build_resolvers()
    for param, entity_id in ids.items():
        assert resolvers[param](session, entity_id) == "proj-res", f"{param} resolver"
        assert resolvers[param](session, "nope") is None, f"{param} unknown id"


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _login(client, email) -> str:
    assert client.post("/api/v1/auth/dev-login", json={"email": email}).status_code == 200
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    return token


def test_outsider_denied_on_flat_item_routes(client, session, auth_on):
    owner = _login(client, "owner@acme.co")
    auth = {SESSION_COOKIE: owner}
    ws = client.post(
        "/api/v1/workspaces", json={"name": "acme", "slug": "acme"}, cookies=auth
    ).json()["id"]
    pid = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "acmep"},
        cookies=auth,
    ).json()["id"]
    ids = _seed(session, pid)
    outsider = {SESSION_COOKIE: _login(client, "outsider@evil.co")}

    probes = [
        ("PATCH", f"/api/v1/comments/{ids['comment_id']}"),
        ("DELETE", f"/api/v1/comments/{ids['comment_id']}"),
        ("PATCH", f"/api/v1/calendar-events/{ids['event_id']}"),
        ("DELETE", f"/api/v1/calendar-events/{ids['event_id']}"),
        ("PATCH", f"/api/v1/status-options/{ids['option_id']}"),
        ("DELETE", f"/api/v1/status-options/{ids['option_id']}"),
        ("DELETE", f"/api/v1/calendar-connections/{ids['connection_id']}"),
        ("POST", f"/api/v1/calendar-connections/{ids['connection_id']}/sync"),
    ]
    for method, path in probes:
        r = client.request(method, path, json={}, cookies=outsider)
        assert r.status_code in (403, 404), f"{method} {path} -> {r.status_code} (leak!)"

    # ...and the owner still gets through, proving the resolvers point at the
    # right models rather than 404-ing everyone.
    assert client.patch(
        f"/api/v1/comments/{ids['comment_id']}", json={"body": "edited"}, cookies=auth
    ).status_code == 200
    assert client.patch(
        f"/api/v1/calendar-events/{ids['event_id']}", json={"title": "E2"}, cookies=auth
    ).status_code == 200
    assert client.patch(
        f"/api/v1/status-options/{ids['option_id']}", json={"label": "Held"}, cookies=auth
    ).status_code == 200
