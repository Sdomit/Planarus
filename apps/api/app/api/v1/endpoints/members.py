"""Workspace membership management (Phase 10.1, hosted mode).

RBAC is enforced here (membership is self-contained): only workspace ``owner``s
manage members, with a bootstrap path for claiming an empty workspace and a
guard against removing/demoting the last owner. Enforcement of roles on the
*domain* routes (projects, tasks, …) is a separate slice (P10.2).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.auth_deps import (
    get_current_user,
    require_auth_enabled,
    require_workspace_role,
)
from app.core.exceptions import ConflictError
from app.db.session import get_session
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.member import MemberAddRequest, MemberRead, MemberRoleUpdate
from app.services import auth_service

router = APIRouter(dependencies=[Depends(require_auth_enabled)])


def _require_workspace(session: Session, workspace_id: str) -> Workspace:
    ws = session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return ws


def _member_read(session: Session, member: WorkspaceMember) -> MemberRead:
    user = session.get(User, member.user_id)
    return MemberRead(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        email=user.email if user else "",
        display_name=user.display_name if user else "",
        role=member.role,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get(
    "/workspaces/{workspace_id}/members", response_model=list[MemberRead]
)
def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MemberRead]:
    _require_workspace(session, workspace_id)
    # Any member may see the roster; a non-member gets 403.
    require_workspace_role(session, workspace_id, user, "owner", "editor", "viewer")
    return [
        _member_read(session, m)
        for m in auth_service.list_members(session, workspace_id)
    ]


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    workspace_id: str,
    data: MemberAddRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemberRead:
    _require_workspace(session, workspace_id)
    existing = auth_service.list_members(session, workspace_id)
    target = auth_service.user_by_email(session, data.email)

    if not existing:
        # Bootstrap: an unowned workspace can only be claimed by the caller adding
        # themselves as owner. This avoids a chicken-and-egg with no special script.
        if target is None or target.id != user.id or data.role != "owner":
            raise HTTPException(
                status_code=403,
                detail="the first member must be yourself, added as 'owner'",
            )
    else:
        require_workspace_role(session, workspace_id, user, "owner")
        if target is None:
            raise HTTPException(
                status_code=404,
                detail="no user with that email; they must sign in once first",
            )

    try:
        member = auth_service.add_member(session, workspace_id, target.id, data.role)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    return _member_read(session, member)


@router.patch(
    "/workspaces/{workspace_id}/members/{user_id}", response_model=MemberRead
)
def update_member_role(
    workspace_id: str,
    user_id: str,
    data: MemberRoleUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemberRead:
    _require_workspace(session, workspace_id)
    require_workspace_role(session, workspace_id, user, "owner")
    member = auth_service.get_member(session, workspace_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    if (
        member.role == "owner"
        and data.role != "owner"
        and auth_service.count_owners(session, workspace_id) == 1
    ):
        raise HTTPException(
            status_code=409, detail="cannot demote the last owner"
        )
    member = auth_service.set_member_role(session, member, data.role)
    return _member_read(session, member)


@router.delete(
    "/workspaces/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    workspace_id: str,
    user_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _require_workspace(session, workspace_id)
    require_workspace_role(session, workspace_id, user, "owner")
    member = auth_service.get_member(session, workspace_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    if member.role == "owner" and auth_service.count_owners(session, workspace_id) == 1:
        raise HTTPException(
            status_code=409, detail="cannot remove the last owner"
        )
    auth_service.remove_member(session, member)
