from typing import Optional

from pydantic import BaseModel, Field


class ChecklistItemCreate(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    done: bool = False


class ChecklistItemUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=300)
    done: Optional[bool] = None


class ChecklistItemRead(BaseModel):
    id: str
    task_id: str
    label: str
    done: bool
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
