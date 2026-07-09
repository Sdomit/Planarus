from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/info")
def get_info() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "phase": "8-git-metadata",
    }
