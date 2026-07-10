"""Read-only Git metadata service (Phase 8).

This is the ONLY place in the codebase that shells out to Git, and it runs
nothing but allowlisted read-only commands. There is no mutating Git path
anywhere: no commit, push, checkout, reset, merge, add, rm, or config write.

Safety model:
- No ``shell=True`` and no string interpolation — every command is a fixed argv
  constant; the only variable is the repo path, passed as a separate ``-C`` arg.
- ``_READ_ONLY_VERBS`` is the closed set of Git verbs that only read. ``_run``
  rejects any argv whose verb is outside it, so the guarantee holds at every call
  site (not just for the ``_READ_ONLY_GIT`` constants), and survives ``python -O``.
- Every invocation forces ``core.fsmonitor=`` and ``GIT_OPTIONAL_LOCKS=0`` so a
  target repo's own ``.git/config`` cannot turn a read into code execution
  (``core.fsmonitor`` is run as a program during index refresh — the
  CVE-2021-43891 class) or make ``git status`` rewrite ``.git/index``. Note: the
  folder must still be one the user trusts to point AgentBoard at.
- Bounded per-command timeout; failures degrade to an ``is_repo=False`` result or
  an ``unread`` marker on ``message`` rather than raising or asserting a false
  negative.
"""
import os
import subprocess
from typing import Optional

from app.core.utils import now_utc
from app.schemas.git import GitRepoLink

_TIMEOUT_S = 5

# Fixed argv (verb + flags) for each read. NEVER add a mutating command here.
_READ_ONLY_GIT: dict[str, tuple[str, ...]] = {
    "toplevel": ("rev-parse", "--show-toplevel"),
    "branch": ("branch", "--show-current"),
    "log": ("log", "-1", "--format=%h%x1f%s"),
    "status": ("status", "--porcelain"),
    "remote": ("remote", "-v"),
}

# The complete set of Git verbs that cannot change repo/index/worktree/refs.
# A verb outside this set (commit, push, checkout, reset, add, rm, ...) is a
# mutation and is rejected by _run.
_READ_ONLY_VERBS = frozenset({"rev-parse", "branch", "log", "status", "remote"})

for _key, _argv in _READ_ONLY_GIT.items():
    assert _argv[0] in _READ_ONLY_VERBS, f"non-read-only git command in allowlist: {_key}"

# Config forced ahead of the subcommand on every call — takes precedence over the
# target repo's .git/config. Empty core.fsmonitor disables the fsmonitor program.
_HARDENING = ("-c", "core.fsmonitor=")
# GIT_OPTIONAL_LOCKS=0 stops `git status` from refreshing (writing) .git/index.
_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}


def _run(repo_path: str, argv: tuple[str, ...]) -> tuple[int, str]:
    """Run one allowlisted read-only command in ``repo_path``. Returns
    ``(returncode, stripped stdout)``. Raises ``ValueError`` if the verb is not
    read-only, ``FileNotFoundError`` if Git is absent, and
    ``subprocess.TimeoutExpired`` on timeout — the last two handled by callers."""
    if not argv or argv[0] not in _READ_ONLY_VERBS:
        raise ValueError(f"refusing non-read-only git verb: {argv!r}")
    proc = subprocess.run(
        ["git", "-C", repo_path, *_HARDENING, *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        env=_ENV,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _read(repo_path: str, key: str) -> Optional[str]:
    """Run an allowlisted read; return stripped stdout, or ``None`` if the command
    failed (non-zero exit or subprocess error). ``None`` means "unknown" — never a
    definitive negative, so a failed read is not mistaken for clean/no-remote."""
    try:
        rc, out = _run(repo_path, _READ_ONLY_GIT[key])
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out if rc == 0 else None


def _first_fetch_url(remote_v: str) -> Optional[str]:
    """Pick a fetch URL from ``git remote -v`` output, preferring ``origin``.

    Lines are tab-delimited ``name<TAB>url (fetch|push)``; the URL itself may
    contain spaces (e.g. a Windows path), so split on the tab and peel the
    trailing direction marker rather than whitespace-splitting the whole line.
    """
    fallback: Optional[str] = None
    for line in remote_v.splitlines():
        name, tab, rest = line.partition("\t")
        if not tab:
            continue
        url, _, marker = rest.rpartition(" ")
        if marker != "(fetch)":
            continue
        if name == "origin":
            return url
        fallback = fallback or url
    return fallback


def collect(project_id: str, folder_path: Optional[str]) -> GitRepoLink:
    """Read live Git metadata for a project's folder. Never raises for the
    expected "not a repo / no folder / no git" cases — those return a valid
    ``GitRepoLink`` with ``is_repo=False`` and a ``message``."""
    link = GitRepoLink(project_id=project_id, repo_path=folder_path, checked_at=now_utc())

    if not folder_path:
        link.message = "Project has no folder path set."
        return link
    if not os.path.isdir(folder_path):
        link.message = "Project folder does not exist on disk."
        return link

    try:
        rc, top = _run(folder_path, _READ_ONLY_GIT["toplevel"])
    except FileNotFoundError:
        link.message = "Git is not installed or not on PATH."
        return link
    except subprocess.TimeoutExpired:
        link.message = "Git command timed out."
        return link

    if rc != 0:
        link.message = "Folder is not a Git repository."
        return link

    link.is_repo = True
    link.repo_path = top or folder_path

    # Remaining reads are independent and rc-aware: a failed command leaves its
    # field(s) unset and flags `unread` instead of asserting a false negative.
    unread = False

    branch = _read(folder_path, "branch")
    if branch is None:
        unread = True
    else:
        link.current_branch = branch or None
        link.detached = not branch  # empty on a detached HEAD checkout

    # None here means either an error OR an unborn branch (no commits yet); both
    # correctly leave last_commit_* unset, so this is not counted as `unread`.
    log = _read(folder_path, "log")
    if log:
        sha, _, subject = log.partition("\x1f")
        link.last_commit_sha = sha or None
        link.last_commit_subject = subject or None

    status = _read(folder_path, "status")
    if status is None:
        unread = True
    else:
        changed = [ln for ln in status.splitlines() if ln.strip()]
        link.dirty_count = len(changed)
        link.is_dirty = bool(changed)

    remote = _read(folder_path, "remote")
    if remote is None:
        unread = True
    else:
        link.remote_url = _first_fetch_url(remote)

    if unread:
        link.message = "Some Git metadata could not be read."

    return link
