from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A human identity (Phase 10.1, hosted mode).

    Provider-agnostic: authentication methods (OAuth, the dev provider) attach as
    ``UserIdentity`` rows, so one user can link more than one provider. Users only
    exist when auth is enabled — the local single-user mode has no ``User`` rows.

    Table is ``appuser`` because ``user`` is a reserved word in PostgreSQL; using
    an unreserved name avoids per-dialect identifier quoting.
    """

    __tablename__ = "appuser"

    id: str = Field(primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    display_name: str = Field(max_length=200)
    is_active: bool = Field(default=True)
    # P16.1 (D29): server-admin axis — governs accounts and server management,
    # NOT project data (that stays workspace-role-gated). First user bootstraps
    # to admin; the last active admin can never be demoted or deactivated.
    is_admin: bool = Field(default=False)
    created_at: str
    updated_at: str
