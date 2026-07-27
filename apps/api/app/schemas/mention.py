from typing import Optional

from pydantic import BaseModel


class MentionRead(BaseModel):
    id: str
    project_id: str
    source_doc_id: str
    target_type: str
    target_id: str
    created_at: str
    # Resolved by the endpoint (entity_registry.titles_for), not stored: a
    # "Referenced by" panel needs a label, not just an id, and this spares the
    # frontend a second round-trip to look one up per row.
    source_doc_title: Optional[str] = None

    model_config = {"from_attributes": True}
