"""Recent local MCP activity, for the shell's ambient status indicator."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core import tenant
from app.db.session import get_session
from app.models.user import User
from app.schemas.mcp_activity import McpActivityRead
from app.services import mcp_activity_service

router = APIRouter()


@router.get("/mcp-activity", response_model=list[McpActivityRead])
def list_mcp_activity(
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant.tenant_user),
) -> list[McpActivityRead]:
    # In team mode the indicator is still global in the shell, but only carries
    # activity for workspaces the signed-in person can read.
    workspace_ids = tenant.user_workspace_ids(session, user) if user is not None else None
    return mcp_activity_service.active(session, workspace_ids)
