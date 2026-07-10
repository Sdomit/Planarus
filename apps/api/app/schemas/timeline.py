from typing import Optional

from pydantic import BaseModel


class TimelineEvent(BaseModel):
    id: str
    at: str
    event_type: str
    entity_type: str
    entity_id: Optional[str]
    actor_type: str
    label: str  # human-readable, e.g. "update task — Fix login bug"


class ProjectTimeline(BaseModel):
    project_id: str
    generated_at: str
    events: list[TimelineEvent]
