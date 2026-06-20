from fastapi import APIRouter

from app.api.v1.endpoints import (
    blockers,
    context,
    context_pack,
    decisions,
    docs,
    info,
    phases,
    projects,
    risks,
    stages,
    tasks,
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
router.include_router(docs.router, tags=["docs"])
router.include_router(context_pack.router, tags=["context-pack"])
