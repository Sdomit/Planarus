from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import workspace_role_check_sql


class WorkspaceMember(SQLModel, table=True):
    """Binds a ``User`` to a ``Workspace`` with one RBAC role (Phase 10.1, D19).

    Roles (capability nests owner ⊃ editor ⊃ viewer):
      - ``owner``  — full control, incl. membership management and (from P10.2)
        approve/apply;
      - ``editor`` — create/edit domain state + create proposals;
      - ``viewer`` — read-only.

    Membership management is enforced on these rows now; enforcement of roles on
    the existing domain routes lands in P10.2.
    """

    __tablename__ = "workspacemember"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspacemember_ws_user"
        ),
        CheckConstraint(workspace_role_check_sql(), name="ck_workspacemember_role"),
        Index("ix_workspacemember_workspace_id", "workspace_id"),
        Index("ix_workspacemember_user_id", "user_id"),
    )

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id")
    user_id: str = Field(foreign_key="appuser.id")
    role: str = Field(default="viewer")
    created_at: str
    updated_at: str
