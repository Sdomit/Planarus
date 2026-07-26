from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db.session import get_session
from app.models.status_option import StatusOption
from app.schemas.reorder import ReorderRequest
from app.schemas.status_option import (
    StatusOptionCreate,
    StatusOptionRead,
    StatusOptionUpdate,
)
from app.services import status_option_service

router = APIRouter()


def _to_read(opt: StatusOption) -> StatusOptionRead:
    return StatusOptionRead(
        id=opt.id, key=opt.key, label=opt.label, category=opt.category,
        color=opt.color, sort_order=opt.sort_order, builtin=False,
    )


@router.get("/projects/{project_id}/status-options", response_model=list[StatusOptionRead])
def list_status_options(
    project_id: str,
    entity_type: str = Query(default="task"),
    session: Session = Depends(get_session),
) -> list[StatusOptionRead]:
    return status_option_service.list_status_options(session, project_id, entity_type)


@router.post(
    "/projects/{project_id}/status-options",
    response_model=StatusOptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_status_option(
    project_id: str,
    data: StatusOptionCreate,
    session: Session = Depends(get_session),
) -> StatusOptionRead:
    try:
        opt = status_option_service.create_status_option(session, project_id, data)
    except ValueError as exc:
        detail = str(exc)
        if "project" in detail and "not found" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return _to_read(opt)


@router.post(
    "/projects/{project_id}/status-options/reorder",
    response_model=list[StatusOptionRead],
)
def reorder_status_options(
    project_id: str,
    data: ReorderRequest,
    entity_type: str = Query(default="task"),
    session: Session = Depends(get_session),
) -> list[StatusOptionRead]:
    return status_option_service.reorder_status_options(
        session, project_id, entity_type, data.ids
    )


@router.patch("/status-options/{option_id}", response_model=StatusOptionRead)
def update_status_option(
    option_id: str,
    data: StatusOptionUpdate,
    session: Session = Depends(get_session),
) -> StatusOptionRead:
    opt = status_option_service.update_status_option(session, option_id, data)
    if opt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status option not found")
    return _to_read(opt)


@router.delete("/status-options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_status_option(
    option_id: str,
    session: Session = Depends(get_session),
) -> None:
    try:
        deleted = status_option_service.delete_status_option(session, option_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status option not found")
