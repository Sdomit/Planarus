from fastapi import APIRouter

from app.api.v1.endpoints import info

router = APIRouter()
router.include_router(info.router, tags=["info"])
