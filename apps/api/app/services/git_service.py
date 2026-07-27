"""Read-only Git metadata service (Phase 8).

This is the ONLY place in the codebase that shells out to Git. The default
surface is allowlisted read-only commands; the sole mutations are the gated,
human-clicked exceptions at the bottom of this file — fetch (Phase 12b, refs
only) and commit/merge (Phase 12d, working tree/history) — each behind its own
off-by-default env flag, the local control token and an audit event. There is
still no push, checkout, reset, rm, or config write, and no mutating Git path
reachable by agents, MCP or the external API.

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
  folder must still be one the user trusts to point Planarus at.
- Bounded per-command timeout; failures degrade to an ``is_repo=False`` result or
  an ``unread`` marker on ``message`` rather than raising or asserting a false
  negative.
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.utils import now_utc
from app.schemas.git import (
    GitBranch,
    GitCommitResult,
    GitFetchResult,
    GitMergeResult,
    GitRepoLink,
    GitSnapshot,
    GitWorkingTree,
)

_TIMEOUT_S = 5

# Fixed argv (verb + flags) for each read. NEVER add a mutating command here.
_READ_ONLY_GIT: dict[str, tuple[str, ...]] = {
    "toplevel": ("rev-parse", "--show-toplevel"),
    "branch": ("branch", "--show-current"),
    "log": ("log", "-1", "--format=%h%x1f%s"),
    "status": ("status", "--porcelain"),
    "remote": ("remote", "-v"),
    # Phase 12a repo-cockpit reads — still strictly read-only.
    "branches": (
        "for-each-ref",
        "refs/heads",
        "--sort=-committerdate",
        "--format=%(refname:short)%1f%(upstream:short)%1f%(upstream:track)%1f%(committerdate:iso8601-strict)",
    ),
    "status_v2": ("status", "--porcelain=v2", "--branch"),
    "origin_head": ("rev-parse", "--abbrev-ref", "origin/HEAD"),
}

# The complete set of Git verbs that cannot change repo/index/worktree/refs.
# A verb outside this set (commit, push, checkout, reset, add, rm, ...) is a
# mutation and is rejected by _run.
_READ_ONLY_VERBS = frozenset(
    {"rev-parse", "branch", "log", "status", "remote", "for-each-ref", "rev-list"}
)

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


def _read_argv(repo_path: str, argv: tuple[str, ...]) -> Optional[str]:
    """Run one read-only argv; return stripped stdout, or ``None`` if the command
    failed (non-zero exit or subprocess error). ``None`` means "unknown" — never a
    definitive negative, so a failed read is not mistaken for clean/no-remote."""
    try:
        rc, out = _run(repo_path, argv)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out if rc == 0 else None


def _read(repo_path: str, key: str) -> Optional[str]:
    return _read_argv(repo_path, _READ_ONLY_GIT[key])


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


# --- Repo cockpit snapshot (Phase 12a) --------------------------------------
#
# SHOW, DON'T DO: everything below is read-only through the same _run gate.
# Remote-dependent fields (ahead/behind, needs-pull) are only as fresh as the
# user's own last fetch; ``last_fetched_at`` (.git/FETCH_HEAD mtime, no git
# call) is the honesty stamp the UI must always show.

_SNAPSHOT_TTL_S = 3.0  # "live" = live-on-view + short TTL, never a daemon
_BRANCH_CAP = 50

_SEP = "\x1f"  # matches the %1f in the "branches" format


def _no_merged_argv(default_branch: str) -> tuple[str, ...]:
    # default_branch comes from git's own output (origin_head / for-each-ref),
    # never from user input, and a ref name cannot start with "-".
    return ("branch", "--no-merged", default_branch, "--format=%(refname:short)")


def _divergence_argv(default_branch: str, branch: str) -> tuple[str, ...]:
    return ("rev-list", "--left-right", "--count", f"{default_branch}...{branch}")


def _parse_track(track: str) -> tuple[Optional[int], Optional[int], bool]:
    """``[ahead 1, behind 2]`` / ``[gone]`` / ``""`` → (ahead, behind, gone)."""
    if track == "[gone]":
        return None, None, True
    ahead = behind = 0
    for part in track.strip("[]").split(","):
        part = part.strip()
        try:
            if part.startswith("ahead "):
                ahead = int(part[6:])
            elif part.startswith("behind "):
                behind = int(part[7:])
        except ValueError:
            pass
    return ahead, behind, False


def _parse_branches(out: str, current: Optional[str]) -> list[GitBranch]:
    branches: list[GitBranch] = []
    for line in out.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 4:
            continue
        name, upstream, track, committed_at = parts
        branch = GitBranch(
            name=name, is_current=name == current, committed_at=committed_at or None
        )
        if upstream:
            branch.upstream = upstream
            branch.ahead, branch.behind, branch.gone = _parse_track(track)
        branches.append(branch)
    return branches


def _parse_status_v2(out: str) -> tuple[GitWorkingTree, Optional[str], bool]:
    """``status --porcelain=v2 --branch`` → (counts, branch head, detached)."""
    tree = GitWorkingTree()
    head: Optional[str] = None
    detached = False
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            value = line[len("# branch.head "):]
            if value == "(detached)":
                detached = True
            else:
                head = value
        elif line.startswith("# branch.ab "):
            for token in line[len("# branch.ab "):].split():
                try:
                    if token.startswith("+"):
                        tree.ahead = int(token[1:])
                    elif token.startswith("-"):
                        tree.behind = int(token[1:])
                except ValueError:
                    pass
        elif line.startswith(("1 ", "2 ")):
            xy = line.split(" ", 2)[1]
            if xy[:1] != ".":
                tree.staged += 1
            if xy[1:2] != ".":
                tree.unstaged += 1
        elif line.startswith("u "):
            tree.conflicted += 1
        elif line.startswith("? "):
            tree.untracked += 1
    return tree, head, detached


def _default_branch(repo_path: str, local_names: list[str]) -> Optional[str]:
    head = _read(repo_path, "origin_head")  # e.g. "origin/main"
    if head and "/" in head:
        name = head.split("/", 1)[1]
        if name and name != "HEAD":
            return name
    for name in ("main", "master"):
        if name in local_names:
            return name
    return None


def _last_fetched_at(toplevel: str) -> Optional[str]:
    # ponytail: plain .git/FETCH_HEAD mtime; a worktree/submodule (.git is a
    # file) degrades to None rather than spending a git call resolving gitdir.
    try:
        st = os.stat(os.path.join(toplevel, ".git", "FETCH_HEAD"))
    except OSError:
        return None
    return datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()


def _build_snapshot(project_id: str, folder_path: Optional[str]) -> GitSnapshot:
    """Like ``collect``: never raises for expected cases; every section degrades
    independently, leaving fields unset and flagging ``message`` instead."""
    snap = GitSnapshot(project_id=project_id, repo_path=folder_path, checked_at=now_utc())

    if not folder_path:
        snap.message = "Project has no folder path set."
        return snap
    if not os.path.isdir(folder_path):
        snap.message = "Project folder does not exist on disk."
        return snap

    try:
        rc, top = _run(folder_path, _READ_ONLY_GIT["toplevel"])
    except FileNotFoundError:
        snap.message = "Git is not installed or not on PATH."
        return snap
    except subprocess.TimeoutExpired:
        snap.message = "Git command timed out."
        return snap
    if rc != 0:
        snap.message = "Folder is not a Git repository."
        return snap

    snap.is_repo = True
    snap.repo_path = top or folder_path
    unread = False

    status = _read(folder_path, "status_v2")
    if status is None:
        unread = True
    else:
        snap.working_tree, snap.current_branch, snap.detached = _parse_status_v2(status)

    branches_out = _read(folder_path, "branches")
    all_branches: list[GitBranch] = []
    if branches_out is None:
        unread = True
    else:
        all_branches = _parse_branches(branches_out, snap.current_branch)
        snap.branches_total = len(all_branches)
        snap.branches = all_branches[:_BRANCH_CAP]

    snap.default_branch = _default_branch(folder_path, [b.name for b in all_branches])

    if snap.default_branch:
        merged_out = _read_argv(folder_path, _no_merged_argv(snap.default_branch))
        if merged_out is None:
            unread = True
        else:
            snap.needs_merge = [ln.strip() for ln in merged_out.splitlines() if ln.strip()]

        # ponytail: one rev-list per capped branch (≤50 short local calls,
        # behind the TTL cache). Batch via a single rev-list walk if this is
        # ever slow on a huge repo.
        for branch in snap.branches:
            if branch.name == snap.default_branch:
                branch.ahead_of_default = branch.behind_default = 0
                continue
            div = _read_argv(
                folder_path, _divergence_argv(snap.default_branch, branch.name)
            )
            if div is None:
                continue  # unknown, stays None
            left, _, right = div.partition("\t")
            try:
                branch.behind_default = int(left)
                branch.ahead_of_default = int(right)
            except ValueError:
                pass

    log = _read(folder_path, "log")
    if log:
        sha, _, subject = log.partition("\x1f")
        snap.last_commit_sha = sha or None
        snap.last_commit_subject = subject or None

    remote = _read(folder_path, "remote")
    if remote is None:
        unread = True
    else:
        snap.remote_url = _first_fetch_url(remote)

    snap.last_fetched_at = _last_fetched_at(snap.repo_path)

    if unread:
        snap.message = "Some Git metadata could not be read."
    return snap


# ponytail: module-global TTL dict keyed by project id — right for a local
# single-process app; revisit if the API ever runs multi-worker.
_snapshot_cache: dict[str, tuple[float, GitSnapshot]] = {}


def snapshot(project_id: str, folder_path: Optional[str]) -> GitSnapshot:
    """TTL-cached repo cockpit read (see ``_SNAPSHOT_TTL_S``)."""
    now = time.monotonic()
    hit = _snapshot_cache.get(project_id)
    if hit is not None and hit[0] > now:
        return hit[1]
    snap = _build_snapshot(project_id, folder_path)
    _snapshot_cache[project_id] = (now + _SNAPSHOT_TTL_S, snap)
    return snap


# --- Explicit fetch: the ONE gated exception to no-mutation (Phase 12b) ------
#
# This is the sole place Planarus mutates a repo, and it is deliberately kept
# OUT of the read-only machinery:
#   - "fetch" is NOT in _READ_ONLY_VERBS, so `_run` still refuses it (the
#     read-only gate never learns to fetch — verified in test_git_readonly).
#   - `_run_fetch` is a separate subprocess call with a fixed argv, longer
#     network timeout, and no `shell`. It updates remote-tracking refs +
#     FETCH_HEAD only; the working tree and local branches are never touched.
#   - Planarus never auto-fetches: this runs only from a human click, behind
#     PLANARUS_GIT_FETCH_ENABLED (off by default) and the local control token
#     (enforced at the endpoint), plus an in-process min-interval rate limit.

_FETCH_TIMEOUT_S = 30  # network op — generous vs the 5s read timeout
_MIN_FETCH_INTERVAL_S = 10.0  # ponytail: in-process per-project min interval

# The fixed fetch argv. Kept as a module constant so the mutation surface is a
# single, greppable, reviewable line. --prune drops stale remote-tracking refs;
# the remote name is git's own (validated below), never free user input.
_FETCH_VERB = "fetch"
_FETCH_FLAGS = ("--prune",)

# Per-project monotonic timestamp of the last fetch we ran (rate-limit state).
_last_fetch_at: dict[str, float] = {}


def _pick_remote(repo_path: str) -> Optional[str]:
    """Choose a remote to fetch, preferring ``origin``. Read via the read-only
    ``remote`` command, so the name comes from git itself, not user input."""
    out = _read(repo_path, "remote")
    if not out:
        return None
    names: list[str] = []
    for line in out.splitlines():
        name = line.split("\t", 1)[0].strip()
        # A ref/remote name can never start with '-'; refuse anything odd so it
        # can't be read as a flag by git.
        if name and not name.startswith("-") and name not in names:
            names.append(name)
    if not names:
        return None
    return "origin" if "origin" in names else names[0]


def _run_fetch(repo_path: str, remote: str) -> tuple[int, str]:
    """Run the one blessed mutation: ``git fetch --prune <remote>``. Fixed argv,
    no shell, bounded by a longer network timeout. Refs + FETCH_HEAD only."""
    if remote.startswith("-"):
        raise ValueError(f"refusing suspicious remote name: {remote!r}")
    proc = subprocess.run(
        ["git", "-C", repo_path, *_HARDENING, _FETCH_VERB, *_FETCH_FLAGS, remote],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_FETCH_TIMEOUT_S,
        env=_ENV,
        check=False,
    )
    # stderr carries fetch progress/errors; stdout is usually empty.
    return proc.returncode, (proc.stderr or proc.stdout).strip()


def fetch(project_id: str, folder_path: Optional[str]) -> GitFetchResult:
    """Human-triggered fetch of remote-tracking refs. Raises ``ConflictError``
    when disabled (the env gate); otherwise degrades to a result status and
    never raises for the expected cases, so a failure never blocks the offline
    cockpit. The endpoint enforces the control token and writes the audit event.
    """
    if not settings.git_fetch_enabled:
        raise ConflictError(
            "git fetch is disabled — set PLANARUS_GIT_FETCH_ENABLED=true to "
            "allow the explicit, human-clicked fetch (remote-tracking refs only)"
        )

    def _result(status: str, message: Optional[str], remote: Optional[str]) -> GitFetchResult:
        # Always attach the current cockpit state so the UI can refresh its stamp.
        return GitFetchResult(
            project_id=project_id,
            status=status,
            message=message,
            remote=remote,
            snapshot=snapshot(project_id, folder_path),
        )

    if not folder_path or not os.path.isdir(folder_path):
        return _result("failed", "Project folder is missing or not on disk.", None)

    try:
        rc, top = _run(folder_path, _READ_ONLY_GIT["toplevel"])
    except FileNotFoundError:
        return _result("failed", "Git is not installed or not on PATH.", None)
    except subprocess.TimeoutExpired:
        return _result("failed", "Git command timed out.", None)
    if rc != 0:
        return _result("failed", "Folder is not a Git repository.", None)

    remote = _pick_remote(folder_path)
    if remote is None:
        return _result("no_remote", "This repository has no remote to fetch from.", None)

    now = time.monotonic()
    last = _last_fetch_at.get(project_id)
    if last is not None and now - last < _MIN_FETCH_INTERVAL_S:
        wait = int(_MIN_FETCH_INTERVAL_S - (now - last)) + 1
        return _result(
            "rate_limited",
            f"Fetched moments ago — try again in ~{wait}s.",
            remote,
        )

    try:
        frc, ferr = _run_fetch(folder_path, remote)
    except (subprocess.TimeoutExpired, OSError) as exc:
        _last_fetch_at[project_id] = now  # count the attempt toward the interval
        return _result("failed", f"Fetch failed: {type(exc).__name__}.", remote)

    _last_fetch_at[project_id] = now
    if frc != 0:
        # Truncate git's stderr; never surface tokens/paths verbatim beyond this.
        return _result("failed", (ferr or "git fetch returned non-zero.")[:300], remote)

    # Success: the FETCH_HEAD stamp and remote-tracking refs changed, so the
    # cached snapshot is stale — drop it and recompute fresh for the response.
    _snapshot_cache.pop(project_id, None)
    return _result("ok", None, remote)


# --- Phase 12d: gated commit + merge -----------------------------------------
#
# Same doctrine as fetch, wider blast radius, so a separate flag: these touch
# the working tree and local history. Both run only from a human click in the
# local UI, behind PLANARUS_GIT_WRITE_ENABLED (off by default) plus the local
# control token, and every attempt is audited at the endpoint. Agents, MCP and
# the external API still have no mutating Git path.
#
# The write allowlist is as closed as the read one: add, commit, merge. No
# push, checkout, reset, rm. A conflicted merge is aborted server-side so the
# cockpit never leaves a half-merged tree behind.

_WRITE_TIMEOUT_S = 30  # hooks and big merges are slower than 5s reads
_WRITE_VERBS = frozenset({"add", "commit", "merge"})


def _run_write(repo_path: str, argv: tuple[str, ...]) -> tuple[int, str]:
    """Run one allowlisted mutating command. Mirrors ``_run`` but against the
    write allowlist, with the longer timeout; stderr wins for the message."""
    if not argv or argv[0] not in _WRITE_VERBS:
        raise ValueError(f"refusing non-allowlisted git write verb: {argv!r}")
    proc = subprocess.run(
        ["git", "-C", repo_path, *_HARDENING, *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_WRITE_TIMEOUT_S,
        env=_ENV,
        check=False,
    )
    return proc.returncode, (proc.stderr or proc.stdout).strip()


def _write_preamble(folder_path: Optional[str]) -> Optional[str]:
    """Shared repo checks for commit/merge; a message means "refuse with it"."""
    if not settings.git_write_enabled:
        raise ConflictError(
            "git commit/merge is disabled — set PLANARUS_GIT_WRITE_ENABLED=true "
            "to allow the explicit, human-clicked working-tree actions"
        )
    if not folder_path or not os.path.isdir(folder_path):
        return "Project folder is missing or not on disk."
    try:
        rc, _ = _run(folder_path, _READ_ONLY_GIT["toplevel"])
    except FileNotFoundError:
        return "Git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return "Git command timed out."
    if rc != 0:
        return "Folder is not a Git repository."
    return None


def commit(project_id: str, folder_path: Optional[str], message: str) -> GitCommitResult:
    """Stage everything and commit with ``message``. Raises ``ConflictError``
    when the env gate is off; otherwise degrades to a status like fetch does."""

    def _result(status: str, msg: Optional[str], sha: Optional[str] = None) -> GitCommitResult:
        if status == "ok":
            _snapshot_cache.pop(project_id, None)
        return GitCommitResult(
            project_id=project_id, status=status, message=msg, sha=sha,
            snapshot=snapshot(project_id, folder_path),
        )

    refusal = _write_preamble(folder_path)
    if refusal:
        return _result("failed", refusal)
    assert folder_path is not None  # narrowed by _write_preamble

    text = message.strip()
    if not text:
        return _result("failed", "Commit message is empty.")

    porcelain = _read_argv(folder_path, _READ_ONLY_GIT["status"])
    if porcelain is not None and porcelain == "":
        return _result("clean", "Nothing to commit — the working tree is clean.")

    try:
        rc, out = _run_write(folder_path, ("add", "-A"))
        if rc != 0:
            return _result("failed", (out or "git add returned non-zero.")[:300])
        rc, out = _run_write(folder_path, ("commit", "-m", text))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _result("failed", f"Commit failed: {type(exc).__name__}.")
    if rc != 0:
        # Typical causes worth surfacing verbatim (trimmed): missing user.name /
        # user.email identity, a failing hook, or a race that emptied the stage.
        return _result("failed", (out or "git commit returned non-zero.")[:300])

    sha = _read_argv(folder_path, ("rev-parse", "--short", "HEAD"))
    return _result("ok", None, sha)


def merge(project_id: str, folder_path: Optional[str], branch: str) -> GitMergeResult:
    """Merge local ``branch`` into the current branch. Refuses on a dirty tree;
    aborts and reports on conflict. Raises ``ConflictError`` when gated off."""

    def _result(status: str, msg: Optional[str], sha: Optional[str] = None) -> GitMergeResult:
        if status == "ok":
            _snapshot_cache.pop(project_id, None)
        return GitMergeResult(
            project_id=project_id, status=status, message=msg, sha=sha,
            snapshot=snapshot(project_id, folder_path),
        )

    refusal = _write_preamble(folder_path)
    if refusal:
        return _result("failed", refusal)
    assert folder_path is not None  # narrowed by _write_preamble

    name = branch.strip()
    # A ref name can never start with '-'; refuse anything git could read as a
    # flag, then require it to be a real local branch (also kills typos).
    if not name or name.startswith("-"):
        return _result("failed", f"Refusing suspicious branch name: {name!r}")
    heads = _read_argv(
        folder_path, ("for-each-ref", "--format=%(refname:short)", "refs/heads")
    )
    if heads is None:
        return _result("failed", "Could not read the local branch list.")
    if name not in heads.splitlines():
        return _result("failed", f"'{name}' is not a local branch.")

    current = _read_argv(folder_path, _READ_ONLY_GIT["branch"])
    if not current:
        return _result("failed", "Cannot merge onto a detached HEAD.")
    if name == current:
        return _result("failed", f"'{name}' is already the current branch.")

    porcelain = _read_argv(folder_path, _READ_ONLY_GIT["status"])
    if porcelain is None:
        return _result("failed", "Could not read the working-tree state.")
    if porcelain != "":
        return _result(
            "dirty", "The working tree has uncommitted changes — commit or stash first."
        )

    try:
        rc, out = _run_write(folder_path, ("merge", "--no-edit", name))
    except (subprocess.TimeoutExpired, OSError) as exc:
        # State unknown after a timeout mid-merge: try to abort, best-effort.
        try:
            _run_write(folder_path, ("merge", "--abort"))
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return _result("failed", f"Merge failed: {type(exc).__name__}.")

    if rc != 0:
        # Conflict (or any refusal after the merge started): abort so the tree
        # is never left half-merged. MERGE_HEAD may not exist when git refused
        # up front — the abort then fails harmlessly.
        try:
            _run_write(folder_path, ("merge", "--abort"))
        except (subprocess.TimeoutExpired, OSError):
            pass
        status = "conflict" if "CONFLICT" in out else "failed"
        return _result(status, (out or "git merge returned non-zero.")[:300])

    sha = _read_argv(folder_path, ("rev-parse", "--short", "HEAD"))
    return _result("ok", None, sha)
