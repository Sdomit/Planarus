from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    agent_runs,
    api_clients,
    approvals,
    auth,
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

from fastapi import Depends

from app.core.tenant import tenant_guard

# P10.2b: one registry-driven guard (no-op when auth is off) applied to every
# project-scoped domain router at include time — full tenant isolation without a
# per-route edit. NOT applied to: info (global), auth/members/workspaces/projects
# (own enforcement in P10.1/P10.2), approvals + api-clients (own workspace-scoped
# guards below and in those endpoints).
_GUARD = [Depends(tenant_guard)]

router = APIRouter()
router.include_router(info.router, tags=["info"])
router.include_router(auth.router, tags=["auth"])
# P16.1: the admin plane (account lifecycle) — 404s entirely when auth is off,
# like auth/members; admin-gated + control-token-gated inside.
router.include_router(admin.router, tags=["admin"])
router.include_router(members.router, tags=["members"])
router.include_router(workspaces.router, tags=["workspaces"])
router.include_router(projects.router, tags=["projects"])
router.include_router(context.router, tags=["context"], dependencies=_GUARD)
router.include_router(phases.router, tags=["phases"], dependencies=_GUARD)
router.include_router(stages.router, tags=["stages"], dependencies=_GUARD)
router.include_router(status_options.router, tags=["status-options"], dependencies=_GUARD)
router.include_router(tasks.router, tags=["tasks"], dependencies=_GUARD)
router.include_router(decisions.router, tags=["decisions"], dependencies=_GUARD)
router.include_router(risks.router, tags=["risks"], dependencies=_GUARD)
router.include_router(blockers.router, tags=["blockers"], dependencies=_GUARD)
router.include_router(milestones.router, tags=["milestones"], dependencies=_GUARD)
router.include_router(todos.router, tags=["todos"], dependencies=_GUARD)
router.include_router(
    calendar_events.router, tags=["calendar-events"], dependencies=_GUARD
)
router.include_router(calendar.router, tags=["calendar"], dependencies=_GUARD)
router.include_router(calendar_sync.router, tags=["calendar-sync"], dependencies=_GUARD)
router.include_router(
    checklist_items.router, tags=["checklist-items"], dependencies=_GUARD
)
router.include_router(comments.router, tags=["comments"], dependencies=_GUARD)
router.include_router(links.router, tags=["links"], dependencies=_GUARD)
router.include_router(docs.router, tags=["docs"], dependencies=_GUARD)
router.include_router(context_pack.router, tags=["context-pack"], dependencies=_GUARD)
router.include_router(git.router, tags=["git"], dependencies=_GUARD)
router.include_router(approvals.router, tags=["approvals"])
router.include_router(api_clients.router, tags=["api-clients"])
# P17.3: outbound webhooks — workspace-owner + control-token gated (own guards),
# and 404 entirely unless webhook encryption is configured.
router.include_router(webhooks.router, tags=["webhooks"])
router.include_router(roadmap.router, tags=["roadmap"], dependencies=_GUARD)
router.include_router(timeline.router, tags=["timeline"], dependencies=_GUARD)
router.include_router(agent_runs.router, tags=["agent-runs"], dependencies=_GUARD)
router.include_router(notifications.router, tags=["notifications"], dependencies=_GUARD)
router.include_router(sync.router, tags=["sync"], dependencies=_GUARD)
# Settings is a global, control-token-gated surface (no project scope), so it is
# not under _GUARD — like info/auth/members/workspaces above.
router.include_router(settings.router, tags=["settings"])
# P17.2: read-only MCP connection metadata for the Integrations hub — global and
# ungated like info; discloses no capability value and no raw path in team mode.
router.include_router(mcp.router, tags=["integrations"])
# P17.5: serves the curated GPT Actions OpenAPI contract for copy-paste into a
# private ChatGPT — a pure mirror of app/api/external/openapi.py's builders.
router.include_router(gpt.router, tags=["integrations"])
