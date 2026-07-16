from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.blocker import BlockerCreate, BlockerRead, BlockerUpdate
from app.services import blocker_service

router = APIRouter()


@router.get("/projects/{project_id}/blockers", response_model=list[BlockerRead])
def list_blockers(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[BlockerRead]:
    return blocker_service.list_blockers(session, project_id)


@router.post(
    "/projects/{project_id}/blockers",
    response_model=BlockerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_blocker(
    project_id: str,
    data: BlockerCreate,
    session: Session = Depends(get_session),
) -> BlockerRead:
    try:
        return blocker_service.create_blocker(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/blockers/{blocker_id}", response_model=BlockerRead)
def update_blocker(
    blocker_id: str,
    data: BlockerUpdate,
    session: Session = Depends(get_session),
) -> BlockerRead:
    try:
        blocker = blocker_service.update_blocker(session, blocker_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if blocker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Blocker not found"
        )
    return blocker


@router.delete("/blockers/{blocker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blocker(
    blocker_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not blocker_service.delete_blocker(session, blocker_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Blocker not found"
        )
