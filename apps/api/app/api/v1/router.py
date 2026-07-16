from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_runs,
    api_clients,
    approvals,
    auth,
    blockers,
    checklist_items,
    comments,
    context,
    context_pack,
    decisions,
    docs,
    git,
    info,
    links,
    members,
    milestones,
    notifications,
    phases,
    projects,
    risks,
    roadmap,
    stages,
    tasks,
    timeline,
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
router.include_router(members.router, tags=["members"])
router.include_router(workspaces.router, tags=["workspaces"])
router.include_router(projects.router, tags=["projects"])
router.include_router(context.router, tags=["context"], dependencies=_GUARD)
router.include_router(phases.router, tags=["phases"], dependencies=_GUARD)
router.include_router(stages.router, tags=["stages"], dependencies=_GUARD)
router.include_router(tasks.router, tags=["tasks"], dependencies=_GUARD)
router.include_router(decisions.router, tags=["decisions"], dependencies=_GUARD)
router.include_router(risks.router, tags=["risks"], dependencies=_GUARD)
router.include_router(blockers.router, tags=["blockers"], dependencies=_GUARD)
router.include_router(milestones.router, tags=["milestones"], dependencies=_GUARD)
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
router.include_router(roadmap.router, tags=["roadmap"], dependencies=_GUARD)
router.include_router(timeline.router, tags=["timeline"], dependencies=_GUARD)
router.include_router(agent_runs.router, tags=["agent-runs"], dependencies=_GUARD)
router.include_router(notifications.router, tags=["notifications"], dependencies=_GUARD)
