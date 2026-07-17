from typing import Optional

from pydantic import BaseModel, Field


class TodoCreate(BaseModel):
    label: str = Field(min_length=1, max_length=500)
    parent_id: Optional[str] = None  # nest under an existing todo (same project)
    done: bool = False


class TodoUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=500)
    done: Optional[bool] = None
    # parent_id is set explicitly (incl. to null to outdent to top level); the
    # service uses exclude_unset so omitting it leaves the parent unchanged.
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None


class TodoRead(BaseModel):
    id: str
    project_id: str
    parent_id: Optional[str]
    label: str
    done: bool
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
