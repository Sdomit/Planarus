"""Cross-machine sync endpoints (Phase 10.6c).

Project-scoped, so they ride the router-level ``tenant_guard`` (GET → read role,
POST → write role; 404 for a project the caller can't see). A client pulls
``/sync/snapshot`` (what the remote holds), diffs it against its stored baseline +
local manifest, applies the remote's one-sided changes locally, then pushes its own
one-sided changes to ``/sync/push``. The push is project-scope-restricted so it can
never inject records belonging to another project (see `transport.import_change_set`).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.models.project import Project
from app.schemas.sync import PushRequest, PushResponse, SnapshotResponse
from app.sync import ScopeViolation, build_snapshot, import_change_set
from app.sync.diff import Change, ChangeKind
from app.sync.manifest import build_manifest

router = APIRouter()


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _manifest_rows(session: Session, project_id: str) -> list[list[str]]:
    return [[t, i, sig] for (t, i), sig in sorted(build_manifest(session, project_id).items())]


@router.get("/projects/{project_id}/sync/snapshot", response_model=SnapshotResponse)
def sync_snapshot(
    project_id: str, session: Session = Depends(get_session)
) -> SnapshotResponse:
    _require_project(session, project_id)
    return SnapshotResponse(**build_snapshot(session, project_id))


@router.post("/projects/{project_id}/sync/push", response_model=PushResponse)
def sync_push(
    project_id: str,
    body: PushRequest,
    session: Session = Depends(get_session),
) -> PushResponse:
    _require_project(session, project_id)
    changes = [
        Change((c.entity_type, c.entity_id), ChangeKind(c.kind)) for c in body.changes
    ]
    try:
        import_change_set(
            session, changes, body.records, restrict_project_id=project_id
        )
    except ScopeViolation as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return PushResponse(applied=len(changes), manifest=_manifest_rows(session, project_id))
