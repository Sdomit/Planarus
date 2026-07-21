from typing import Optional

from pydantic import BaseModel


class GitRepoLink(BaseModel):
    """Read-only snapshot of a project folder's Git state.

    Computed live from allowlisted read-only Git commands (see
    ``app.services.git_service``); Planarus never persists or mutates Git state.
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


# --- Repo cockpit snapshot (Phase 12a) --------------------------------------


class GitBranch(BaseModel):
    """One local branch. ``ahead``/``behind`` are vs its upstream (``None`` when
    no upstream is set); ``*_default`` are vs the repo's default branch. ``None``
    always means "could not be read", never zero."""

    name: str
    is_current: bool = False
    upstream: Optional[str] = None
    ahead: Optional[int] = None
    behind: Optional[int] = None
    gone: bool = False
    committed_at: Optional[str] = None
    ahead_of_default: Optional[int] = None
    behind_default: Optional[int] = None


class GitWorkingTree(BaseModel):
    """Working-tree counts from ``status --porcelain=v2``. ``ahead``/``behind``
    are the current branch vs its upstream (``None`` without an upstream)."""

    staged: int = 0
    unstaged: int = 0
    untracked: int = 0
    conflicted: int = 0
    ahead: Optional[int] = None
    behind: Optional[int] = None


class GitSnapshot(BaseModel):
    """Full read-only repo cockpit state, computed live from allowlisted
    read-only Git commands. SHOW, DON'T DO: nothing here mutates the repo, and
    remote-dependent fields are only as fresh as the user's own last fetch —
    ``last_fetched_at`` is the honesty stamp (``.git/FETCH_HEAD`` mtime)."""

    project_id: str
    repo_path: Optional[str] = None
    is_repo: bool = False
    message: Optional[str] = None
    checked_at: str
    current_branch: Optional[str] = None
    detached: bool = False
    default_branch: Optional[str] = None
    last_commit_sha: Optional[str] = None
    last_commit_subject: Optional[str] = None
    remote_url: Optional[str] = None
    branches: list[GitBranch] = []
    branches_total: int = 0
    needs_merge: list[str] = []
    working_tree: Optional[GitWorkingTree] = None
    last_fetched_at: Optional[str] = None


# --- Read-only PR layer via the GitHub CLI (Phase 12c) ----------------------


class GitPullRequest(BaseModel):
    """One open pull request, as reported by the local gh CLI (read-only)."""

    number: int
    title: str
    state: str
    is_draft: bool = False
    head: Optional[str] = None
    base: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    updated_at: Optional[str] = None
    review_decision: Optional[str] = None


class GitPrSummary(BaseModel):
    """Read-only open-PR summary from the local GitHub CLI. ``status``:

    - ``ok``      — gh ran; ``prs`` is the open-PR list (may be empty)
    - ``no_gh``   — the gh binary is not installed / not on PATH
    - ``no_auth`` — gh is installed but not signed in (hint in ``message``)
    - ``failed``  — gh errored (no GitHub remote, network, parse; see message)

    Zero stored tokens: gh's own keyring holds the credential. Computed only on
    an explicit human click in the local UI (never polled), behind a short TTL.
    """

    project_id: str
    status: str = "failed"
    authenticated: bool = False
    message: Optional[str] = None
    prs: list[GitPullRequest] = []
    checked_at: str


class GitFetchResult(BaseModel):
    """Outcome of the one gated exception (Phase 12b): a human-clicked fetch of
    remote-tracking refs. ``status``:

    - ``ok``          — fetch ran; ``snapshot`` is the refreshed post-fetch state
    - ``no_remote``   — the repo has no remote to fetch from
    - ``rate_limited``— fetched too recently (min-interval); no network hit
    - ``failed``      — the fetch was attempted but errored (message explains)

    The working tree and local branches are never touched — refs + FETCH_HEAD
    only. ``snapshot`` is always the current cockpit state so the UI can refresh
    the staleness stamp regardless of outcome.
    """

    project_id: str
    status: str
    message: Optional[str] = None
    remote: Optional[str] = None
    snapshot: Optional[GitSnapshot] = None
