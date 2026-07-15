from typing import Optional

from pydantic import BaseModel


class GitRepoLink(BaseModel):
    """Read-only snapshot of a project folder's Git state.

    Computed live from allowlisted read-only Git commands (see
    ``app.services.git_service``); Approvo never persists or mutates Git state.
    When the folder is missing or not a repo, ``is_repo`` is ``False`` and
    ``message`` explains why — the response is still a valid 200 body.

    ponytail: live-only, no DB cache table. Git reads are instant, so the
    ``GitRepoLink`` cache in docs/plan/03-data-model.md would only add staleness.
    Add the cache table when a repo grows large enough that a read is slow.
    """

    project_id: str
    repo_path: Optional[str] = None
    is_repo: bool = False
    current_branch: Optional[str] = None
    detached: bool = False
    last_commit_sha: Optional[str] = None
    last_commit_subject: Optional[str] = None
    is_dirty: bool = False
    dirty_count: int = 0
    remote_url: Optional[str] = None
    message: Optional[str] = None
    checked_at: str
