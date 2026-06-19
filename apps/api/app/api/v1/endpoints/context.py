from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.fsmemory.regenerator import RegenReport
from app.schemas.context_file import (
    ContextFileContent,
    ContextFileDiff,
    ContextFileRead,
    ContextFileUpdate,
    FileOutcomeRead,
    RegenReportRead,
)
from app.services import context_service, project_service

router = APIRouter()


def _report_to_read(report: RegenReport) -> RegenReportRead:
    return RegenReportRead(
        project_id=report.project_id,
        generated_at=report.generated_at,
        written=report.written_count,
        drifted=report.drifted_count,
        outcomes=[
            FileOutcomeRead(
                relative_path=o.relative_path,
                kind=o.kind,
                status=o.status,
                pinned=o.pinned,
                drifted=o.drifted,
            )
            for o in report.outcomes
        ],
    )


@router.post(
    "/projects/{project_id}/context/regenerate",
    response_model=RegenReportRead,
)
def regenerate_context(
    project_id: str,
    session: Session = Depends(get_session),
) -> RegenReportRead:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if not project.folder_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no folder_path; set one before regenerating context.",
        )
    report = context_service.provision_and_regenerate(
        session, project, actor_type="human"
    )
    return _report_to_read(report)


@router.get("/context-files", response_model=list[ContextFileRead])
def list_context_files(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[ContextFileRead]:
    return context_service.list_context_files(session, project_id)


@router.get(
    "/context-files/{context_file_id}/content",
    response_model=ContextFileContent,
)
def get_context_file_content(
    context_file_id: str,
    session: Session = Depends(get_session),
) -> ContextFileContent:
    cf = context_service.get_context_file(session, context_file_id)
    if cf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Context file not found"
        )
    content, drifted = context_service.read_content(session, cf)
    return ContextFileContent(
        relative_path=cf.relative_path, content=content, drifted=drifted
    )


@router.get(
    "/context-files/{context_file_id}/diff",
    response_model=ContextFileDiff,
)
def get_context_file_diff(
    context_file_id: str,
    session: Session = Depends(get_session),
) -> ContextFileDiff:
    cf = context_service.get_context_file(session, context_file_id)
    if cf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Context file not found"
        )
    diff = context_service.compute_diff(session, cf)
    return ContextFileDiff(relative_path=cf.relative_path, diff=diff)


@router.patch("/context-files/{context_file_id}", response_model=ContextFileRead)
def update_context_file(
    context_file_id: str,
    data: ContextFileUpdate,
    session: Session = Depends(get_session),
) -> ContextFileRead:
    cf = context_service.set_pinned(session, context_file_id, data.pinned)
    if cf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Context file not found"
        )
    return cf
