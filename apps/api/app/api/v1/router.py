"""v1 route table — every router declares exactly one classification (#124).

Tenant protection used to be opt-in: ``include_router(..., dependencies=_GUARD)``
on the routers someone remembered. A new project-scoped router added without
``_GUARD`` was simply unguarded, and ``test_tenant_route_coverage`` could not see
it — that test proves the *guarded* set resolves a tenant, not that the guarded
set is complete.

So the registration is now a table. A router reaches the app only by naming a
``Plane``, the loop at the bottom attaches ``_GUARD`` to every ``Plane.TENANT``
entry, and ``tests/test_route_classification.py`` fails CI on a mounted route
whose tag has no entry. Forgetting the guard is no longer possible; forgetting
the *classification* is what breaks, loudly, in CI.
"""
from enum import Enum

from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    admin,
    agent_runs,
    api_clients,
    approvals,
    auth,
    backups,
    blockers,
    calendar,
    calendar_events,
    calendar_sync,
    checklist_items,
    comments,
    context,
    context_pack,
    decisions,
    docs,
    git,
    gpt,
    info,
    links,
    mcp,
    members,
    milestones,
    notifications,
    phases,
    projects,
    risks,
    roadmap,
    settings,
    stages,
    status_options,
    sync,
    tasks,
    timeline,
    todos,
    webhooks,
    workspaces,
)
from app.core.tenant import tenant_guard


class Plane(str, Enum):
    """How a router is protected. Exactly one per router, no default."""

    #: Project-scoped. ``_GUARD`` is attached here, not by the caller.
    TENANT = "tenant"
    #: Tenant-scoped but enforced inside the endpoints — the reason names where.
    TENANT_SELF_ENFORCED = "tenant-self-enforced"
    #: Server-admin / account lifecycle. 404s entirely when auth is off.
    ADMIN = "admin"
    #: Authenticated self-service (own session, no tenant identifier).
    SELF_SERVICE = "self-service"
    #: Global server-management surface, control-token gated.
    LOCAL_CONTROL = "local-control"
    #: Deliberately global and ungated. Discloses no tenant data.
    GLOBAL = "global"


_GUARD = [Depends(tenant_guard)]

# (module, tag, plane, reason). The reason is required for everything except
# ``Plane.TENANT`` — where the guard is the reason — so that "this route is not
# tenant-guarded" is always a decision someone wrote down and a reviewer can
# check. Order is route-matching order: keep it.
ROUTER_PLANES: list[tuple[object, str, Plane, str]] = [
    (info, "info", Plane.GLOBAL, "server/build metadata; no tenant data"),
    (auth, "auth", Plane.SELF_SERVICE, "session lifecycle; 404s when auth is off"),
    (admin, "admin", Plane.ADMIN, "P16.1 account lifecycle; admin + control-token gated inside"),
    (members, "members", Plane.ADMIN, "workspace membership admin; own role guards (P10.1)"),
    (workspaces, "workspaces", Plane.TENANT_SELF_ENFORCED, "the tenant itself; require_workspace_access inside (P10.2)"),
    (projects, "projects", Plane.TENANT_SELF_ENFORCED, "require_project_access inside; creation checks the target workspace (P10.2)"),
    (context, "context", Plane.TENANT, ""),
    (phases, "phases", Plane.TENANT, ""),
    (stages, "stages", Plane.TENANT, ""),
    (status_options, "status-options", Plane.TENANT, ""),
    (tasks, "tasks", Plane.TENANT, ""),
    (decisions, "decisions", Plane.TENANT, ""),
    (risks, "risks", Plane.TENANT, ""),
    (blockers, "blockers", Plane.TENANT, ""),
    (milestones, "milestones", Plane.TENANT, ""),
    (todos, "todos", Plane.TENANT, ""),
    (calendar_events, "calendar-events", Plane.TENANT, ""),
    (calendar, "calendar", Plane.TENANT, ""),
    # One route here is an OAuth callback carrying no resolvable identifier; it is
    # authorized by the signed, transaction-bound state (#113) and exempted by
    # name in tests/test_tenant_route_coverage.py::GLOBAL_ROUTES.
    (calendar_sync, "calendar-sync", Plane.TENANT, ""),
    (checklist_items, "checklist-items", Plane.TENANT, ""),
    (comments, "comments", Plane.TENANT, ""),
    (links, "links", Plane.TENANT, ""),
    (docs, "docs", Plane.TENANT, ""),
    (context_pack, "context-pack", Plane.TENANT, ""),
    (git, "git", Plane.TENANT, ""),
    (approvals, "approvals", Plane.TENANT_SELF_ENFORCED, "D22 approver gate + workspace-scoped guards inside (P7A)"),
    (api_clients, "api-clients", Plane.TENANT_SELF_ENFORCED, "workspace-scoped guards inside; keys are workspace-owned"),
    (webhooks, "webhooks", Plane.TENANT_SELF_ENFORCED, "P17.3 workspace-owner + control-token gated inside; 404s unless webhook encryption is configured"),
    (roadmap, "roadmap", Plane.TENANT, ""),
    (timeline, "timeline", Plane.TENANT, ""),
    (agent_runs, "agent-runs", Plane.TENANT, ""),
    (notifications, "notifications", Plane.TENANT, ""),
    (sync, "sync", Plane.TENANT, ""),
    (settings, "settings", Plane.LOCAL_CONTROL, "global runtime settings; control-token gated inside, no project scope"),
    (backups, "backups", Plane.LOCAL_CONTROL, "P18.0 local DB backups; control-token + server-admin gated inside"),
    (mcp, "integrations", Plane.GLOBAL, "P17.2 read-only MCP connection metadata; discloses no capability value or raw path"),
    (gpt, "integrations", Plane.GLOBAL, "P17.5 static GPT Actions contract; a mirror of the external openapi builders"),
]

#: tag -> plane, for the classification test. Two routers may share a tag only if
#: they agree on the plane; the test enforces that rather than trusting it.
PLANE_BY_TAG: dict[str, Plane] = {tag: plane for _, tag, plane, _ in ROUTER_PLANES}

router = APIRouter()
for _module, _tag, _plane, _reason in ROUTER_PLANES:
    router.include_router(
        _module.router,  # type: ignore[attr-defined]
        tags=[_tag],
        dependencies=_GUARD if _plane is Plane.TENANT else None,
    )


def route_inventory(app) -> list[tuple[str, str, tuple[str, ...], Plane | None]]:
    """Every mounted ``/api/v1`` method/path with its tags and declared plane.

    ``plane`` is ``None`` for a route whose tags match no table entry — an
    unclassified route, which is what the classification test fails on.

    Takes the app rather than importing it: ``app.main`` imports this module.
    FastAPI keeps included routers as ``_IncludedRouter`` nodes instead of
    flattening them, so the walk has to expand ``effective_route_contexts``.
    """
    rows: list[tuple[str, str, tuple[str, ...], Plane | None]] = []
    for route in app.routes:
        expand = getattr(route, "effective_route_contexts", None)
        if expand is None:
            continue
        for ctx in expand():
            if not ctx.path.startswith("/api/v1"):
                continue
            tags = tuple(sorted(getattr(ctx, "tags", ()) or ()))
            planes = {PLANE_BY_TAG[t] for t in tags if t in PLANE_BY_TAG}
            plane = planes.pop() if len(planes) == 1 else None
            for method in sorted(set(ctx.methods) - {"HEAD", "OPTIONS"}):
                rows.append((method, ctx.path, tags, plane))
    return sorted(rows, key=lambda r: (r[1], r[0]))
