import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import require_local_control
from app.db.session import get_session
from app.fsmemory.project_root import resolve_project_root_or_none
from app.schemas.git import GitFetchResult, GitPrSummary, GitRepoLink, GitSnapshot
from app.services import gh_service, git_service, project_service
from app.services.audit_service import create_audit_event

router = APIRouter()


@router.get("/projects/{project_id}/git", response_model=GitRepoLink)
def get_project_git(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitRepoLink:
    """Live read-only Git metadata for the project's folder. Local UI only."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return git_service.collect(project.id, resolve_project_root_or_none(project))


@router.get("/projects/{project_id}/git/snapshot", response_model=GitSnapshot)
def get_project_git_snapshot(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitSnapshot:
    """Read-only repo cockpit snapshot (Phase 12a): branches with ahead/behind,
    divergence from the default branch, needs-merge list, working-tree counts,
    and the last-fetch freshness stamp. Local UI only — never mounted on MCP or
    the external API. SHOW, DON'T DO: no mutating path exists."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return git_service.snapshot(project.id, resolve_project_root_or_none(project))


@router.get("/projects/{project_id}/git/prs", response_model=GitPrSummary)
def get_project_git_prs(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitPrSummary:
    """Read-only open-PR list via the local GitHub CLI (Phase 12c). An outbound
    READ: it changes nothing (repo, GitHub, gh config) and stores no token —
    gh's own keyring holds the credential. Click-triggered from the local UI
    (never auto-polled) behind a 60s TTL. Local UI only — never mounted on MCP
    or the external API."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return gh_service.pr_summary(project.id, resolve_project_root_or_none(project))


@router.post(
    "/projects/{project_id}/git/fetch",
    response_model=GitFetchResult,
    # The one outbound action in the cockpit: control-token-gated like the
    # approvals/reminders side effects. Local UI only — never MCP/external.
    dependencies=[Depends(require_local_control)],
)
def fetch_project_git(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitFetchResult:
    """Explicit, human-clicked fetch of remote-tracking refs (Phase 12b) — the
    sole documented exception to "SHOW, DON'T DO". Disabled unless
    PLANARUS_GIT_FETCH_ENABLED=true (raises 409 otherwise). Working tree
    untouched; every actual outbound attempt is audited."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = git_service.fetch(project.id, resolve_project_root_or_none(project))

    # Audit only real outbound attempts (a fetch ran or was tried), not the
    # rate-limited/no-remote no-ops. This is the record a Local Truth Bar renders.
    if result.status in ("ok", "failed"):
        create_audit_event(
            session,
            event_type="git_fetch",
            actor_type="human",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            payload_json=json.dumps({"status": result.status, "remote": result.remote}),
        )
        session.commit()
    return result
