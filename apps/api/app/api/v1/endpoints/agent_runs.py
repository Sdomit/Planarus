from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.agent_run import (
    AgentRunAnalytics,
    AgentRunCreate,
    AgentRunRead,
    AgentRunUpdate,
)
from app.services import agent_run_service

router = APIRouter()


@router.get("/projects/{project_id}/agent-runs", response_model=list[AgentRunRead])
def list_agent_runs(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AgentRunRead]:
    return agent_run_service.list_agent_runs(session, project_id, limit=limit)


@router.post(
    "/projects/{project_id}/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run(
    project_id: str,
    data: AgentRunCreate,
    session: Session = Depends(get_session),
) -> AgentRunRead:
    try:
        return agent_run_service.create_agent_run(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(
    "/projects/{project_id}/agent-runs/analytics", response_model=AgentRunAnalytics
)
def agent_run_analytics(
    project_id: str,
    session: Session = Depends(get_session),
) -> AgentRunAnalytics:
    try:
        return agent_run_service.build_analytics(session, project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/agent-runs/{run_id}", response_model=AgentRunRead)
def update_agent_run(
    run_id: str,
    data: AgentRunUpdate,
    session: Session = Depends(get_session),
) -> AgentRunRead:
    run = agent_run_service.update_agent_run(session, run_id, data)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    return run
