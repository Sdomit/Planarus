from fastapi import APIRouter

from app.api.v1.endpoints import info, projects, workspaces

router = APIRouter()
router.include_router(info.router, tags=["info"])
router.include_router(workspaces.router, tags=["workspaces"])
router.include_router(projects.router, tags=["projects"])
