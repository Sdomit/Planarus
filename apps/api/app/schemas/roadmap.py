from pydantic import BaseModel


class RoadmapTaskRollup(BaseModel):
    total: int  # excludes canceled tasks
    done: int
    in_progress: int
    blocked: int


class RoadmapStage(BaseModel):
    id: str
    title: str
    status: str
    sort_order: int
    tasks: RoadmapTaskRollup
    pct_done: int


class RoadmapPhase(BaseModel):
    id: str
    title: str
    status: str
    sort_order: int
    stages: list[RoadmapStage]
    tasks: RoadmapTaskRollup  # includes tasks in this phase's stages
    pct_done: int


class ProjectRoadmap(BaseModel):
    project_id: str
    generated_at: str
    phases: list[RoadmapPhase]
    unphased: RoadmapTaskRollup  # tasks attached to no phase/stage
    totals: RoadmapTaskRollup
    pct_done: int
