from sqlmodel import Field, SQLModel


class Setting(SQLModel, table=True):
    """One runtime setting (Phase 9B). Key/value, not one column per feature.

    `value` is a JSON-encoded scalar (bool/str/int) so types round-trip through a
    single text column. Only the *switch*-tier keys are ever written from the UI;
    secret/ceiling knobs stay in env. Adding feature #N later adds a row, never a
    migration.
    """

    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: str
    updated_at: str
