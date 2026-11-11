from pydantic import BaseModel


class McpActivityRead(BaseModel):
    actor_ref: str
    project_id: str
    project_title: str
    tool_name: str
    last_seen_at: str
