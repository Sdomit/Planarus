from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent_runs,
    api_clients,
    approvals,
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

router = APIRouter()
router.include_router(info.router, tags=["info"])
router.include_router(workspaces.router, tags=["workspaces"])
router.include_router(projects.router, tags=["projects"])
router.include_router(context.router, tags=["context"])
router.include_router(phases.router, tags=["phases"])
router.include_router(stages.router, tags=["stages"])
router.include_router(tasks.router, tags=["tasks"])
router.include_router(decisions.router, tags=["decisions"])
router.include_router(risks.router, tags=["risks"])
router.include_router(blockers.router, tags=["blockers"])
router.include_router(milestones.router, tags=["milestones"])
router.include_router(checklist_items.router, tags=["checklist-items"])
router.include_router(comments.router, tags=["comments"])
router.include_router(links.router, tags=["links"])
router.include_router(docs.router, tags=["docs"])
router.include_router(context_pack.router, tags=["context-pack"])
router.include_router(git.router, tags=["git"])
router.include_router(approvals.router, tags=["approvals"])
router.include_router(api_clients.router, tags=["api-clients"])
router.include_router(roadmap.router, tags=["roadmap"])
router.include_router(timeline.router, tags=["timeline"])
router.include_router(agent_runs.router, tags=["agent-runs"])
router.include_router(notifications.router, tags=["notifications"])
