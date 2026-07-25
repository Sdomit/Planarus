"""Deny-by-default route classification (#124).

``test_tenant_route_coverage`` proves the *guarded* routes resolve a tenant. It
cannot prove the guarded set is complete: a project-scoped router included
without ``_GUARD`` was invisible to it, and to CI.

``app.api.v1.router`` now mounts routers only through ``ROUTER_PLANES``, one
declared ``Plane`` each. These tests make that table load-bearing — an
unclassified route, a tenant-plane route that lost its guard, a guard attached
outside the table, or an unreviewed change to the route surface all fail here.
"""
import os
import re
from pathlib import Path

from app.api.v1.router import PLANE_BY_TAG, ROUTER_PLANES, Plane, route_inventory
from app.core.tenant import _build_resolvers, tenant_guard
from app.main import app

INVENTORY = Path(__file__).parent / "route_inventory.txt"
WRITE_ENV = "PLANARUS_WRITE_ROUTE_INVENTORY"


def _rows():
    rows = route_inventory(app)
    assert len(rows) > 100, "route traversal broke; these tests would pass vacuously"
    return rows


def _is_guarded(ctx) -> bool:
    seen, stack = set(), [ctx.dependant] if ctx.dependant is not None else []
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        if getattr(dep, "call", None) is tenant_guard:
            return True
        stack.extend(dep.dependencies)
    return False


def _guarded_contexts():
    for route in app.routes:
        expand = getattr(route, "effective_route_contexts", None)
        if expand is None:
            continue
        for ctx in expand():
            if ctx.path.startswith("/api/v1"):
                yield ctx, _is_guarded(ctx)


def test_every_route_declares_exactly_one_plane():
    unclassified = [
        f"{method} {path}  tags={list(tags) or '[]'}"
        for method, path, tags, plane in _rows()
        if plane is None
    ]
    assert not unclassified, (
        "These /api/v1 routes carry no single known classification, so nobody has "
        "decided whether they need tenant protection:\n  "
        + "\n  ".join(unclassified)
        + "\n\nFix: mount the router through ROUTER_PLANES in app/api/v1/router.py "
        "with the Plane it belongs to. Plane.TENANT attaches the guard for you; "
        "every other plane needs a written reason."
    )


def test_tenant_plane_routes_are_guarded_and_only_those():
    plane_by_route = {(m, p): plane for m, p, _, plane in _rows()}
    missing, unexpected = [], []
    for ctx, guarded in _guarded_contexts():
        for method in sorted(set(ctx.methods) - {"HEAD", "OPTIONS"}):
            plane = plane_by_route.get((method, ctx.path))
            if plane is Plane.TENANT and not guarded:
                missing.append(f"{method} {ctx.path}")
            elif plane is not Plane.TENANT and guarded:
                unexpected.append(f"{method} {ctx.path}  plane={plane}")

    assert not missing, (
        "Declared Plane.TENANT but tenant_guard is not in the dependency tree — "
        "the guard is attached by the ROUTER_PLANES loop, so this means the route "
        "is mounted somewhere else:\n  " + "\n  ".join(sorted(missing))
    )
    assert not unexpected, (
        "tenant_guard is attached to routes that did not declare Plane.TENANT. "
        "Guarding is not harmful, but it means the table no longer describes "
        "reality — move the router to Plane.TENANT or drop the stray guard:\n  "
        + "\n  ".join(sorted(unexpected))
    )


def test_a_route_carrying_a_tenant_identifier_cannot_leave_the_tenant_planes():
    """The table records decisions; this stops one decision from being wrong.

    Nothing above prevents downgrading a project-scoped router to
    ``Plane.GLOBAL`` with a plausible sentence — the tests would pass and the
    routes would be unguarded. A path parameter the tenant resolvers recognise is
    objective evidence that the route is project-scoped, so it must land in one
    of the two tenant planes: guarded by the table, or self-enforced.
    """
    resolvers = set(_build_resolvers())
    tenant_planes = {Plane.TENANT, Plane.TENANT_SELF_ENFORCED}
    escaped = [
        f"{method} {path}  plane={plane.value if plane else None}  via={sorted(params & resolvers)}"
        for method, path, _, plane in _rows()
        if (params := set(re.findall(r"{(\w+)}", path))) & resolvers
        and plane not in tenant_planes
    ]
    assert not escaped, (
        "These routes carry a path parameter that resolves to a project, but are "
        "classified outside the tenant planes — so no membership or role check "
        "runs for a caller with any valid session:\n  " + "\n  ".join(escaped)
        + "\n\nFix: classify the router Plane.TENANT (the table attaches the "
        "guard), or Plane.TENANT_SELF_ENFORCED with a reason naming the check "
        "inside the endpoints."
    )


def test_planes_without_a_guard_state_a_reason():
    """The point of the table is that "not tenant-guarded" is a written decision."""
    silent = [
        f"{tag} ({plane.value})"
        for _, tag, plane, reason in ROUTER_PLANES
        if plane is not Plane.TENANT and not reason.strip()
    ]
    assert not silent, (
        "These routers opt out of tenant_guard without saying why: "
        + ", ".join(silent)
    )


def test_a_shared_tag_agrees_on_one_plane():
    """Two routers may share a tag (mcp/gpt are both 'integrations') only if they
    classify the same — otherwise PLANE_BY_TAG silently keeps the last one."""
    seen: dict[str, Plane] = {}
    conflicts = []
    for _, tag, plane, _ in ROUTER_PLANES:
        if seen.setdefault(tag, plane) is not plane:
            conflicts.append(f"{tag}: {seen[tag].value} vs {plane.value}")
    assert not conflicts, "Tags classified two ways: " + ", ".join(conflicts)


def test_no_stale_table_entries():
    """An entry for a router that mounts nothing is a rule protecting no route."""
    live = {tag for _, _, tags, _ in _rows() for tag in tags}
    assert not (set(PLANE_BY_TAG) - live), (
        f"ROUTER_PLANES classifies tags that mount no route: "
        f"{sorted(set(PLANE_BY_TAG) - live)}"
    )


def test_route_inventory_matches_the_committed_report():
    """The release-evidence snapshot: route-surface changes show up in the diff.

    Regenerate deliberately, then read the diff before committing it:
        PLANARUS_WRITE_ROUTE_INVENTORY=1 python -m pytest tests/test_route_classification.py
    """
    report = "\n".join(
        f"{plane.value if plane else 'UNCLASSIFIED':<20} {method:<7} {path}"
        for method, path, _, plane in _rows()
    )
    if os.environ.get(WRITE_ENV):
        INVENTORY.write_text(report + "\n", encoding="utf-8")

    assert INVENTORY.exists(), f"missing {INVENTORY.name}; regenerate with {WRITE_ENV}=1"
    committed = INVENTORY.read_text(encoding="utf-8").strip().splitlines()
    current = report.splitlines()
    added = [line for line in current if line not in committed]
    removed = [line for line in committed if line not in current]
    assert not (added or removed), (
        "The /api/v1 route surface changed without updating the classification "
        "report.\nAdded:\n  " + ("\n  ".join(added) or "(none)")
        + "\nRemoved:\n  " + ("\n  ".join(removed) or "(none)")
        + f"\n\nRegenerate with {WRITE_ENV}=1 and review the diff in the PR."
    )


def test_report_lists_every_route_exactly_once():
    rows = [(method, path) for method, path, _, _ in _rows()]
    dupes = {r for r in rows if rows.count(r) > 1}
    assert not dupes, f"routes reported more than once: {sorted(dupes)}"
