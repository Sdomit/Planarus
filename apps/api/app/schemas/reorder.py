from pydantic import BaseModel, Field


class ReorderRequest(BaseModel):
    """A full, ordered list of entity ids for one project. The new `sort_order`
    of each entity is its index in `ids`. The list must contain exactly the
    project's entities of that kind — no missing, extra, or duplicate ids."""

    ids: list[str] = Field(min_length=1)
