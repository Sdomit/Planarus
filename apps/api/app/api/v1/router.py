from fastapi import APIRouter

from app.api.v1.endpoints import context, info, projects, workspaces

router = APIRouter()
router.include_router(info.router, tags=["info"])
router.include_router(workspaces.router, tags=["workspaces"])
router.include_router(projects.router, tags=["projects"])
router.include_router(context.router, tags=["context"])
