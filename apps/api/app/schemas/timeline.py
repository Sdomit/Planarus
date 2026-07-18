from typing import Optional

from pydantic import BaseModel


class TimelineEvent(BaseModel):
    id: str
    at: str
    event_type: str
    entity_type: str
    entity_id: Optional[str]
    actor_type: str
    # P16.0 (D32): who did it, when a signed-in user was in context. Local
    # single-user mode leaves both None and the UI falls back to actor_type.
    actor_id: Optional[str] = None
    actor_display: Optional[str] = None
    label: str  # human-readable, e.g. "update task — Fix login bug"


class ProjectTimeline(BaseModel):
    project_id: str
    generated_at: str
    events: list[TimelineEvent]
