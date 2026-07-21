"""Read-only GitHub CLI PR layer (Phase 12c).

This is the ONLY place in the codebase that shells out to the gh binary, and it
runs nothing but *exact* allowlisted read commands. Zero stored tokens: gh's own
keyring/config holds the credential — Planarus never reads, stores, or logs it.

Safety model (mirrors git_service, stricter):
- ``_run_gh`` accepts an argv only if it is one of the ``_ALLOWED_GH`` constants
  BY VALUE — not a verb allowlist but an exact-argv allowlist, so no flag or
  argument can ever vary at a call site. No ``shell=True``, no interpolation.
- Read commands only. Nothing here can change the repo, GitHub state, or gh
  config: pr merge/close/create/comment, repo, api, alias, extension, … are all
  refused because their argvs are not in the table.
- Never auto-runs: the endpoint is click-triggered from the local UI and
  TTL-cached; there is no poller, scheduler, or daemon.
- Env hardening: prompts, pager, color, and the update notifier are disabled so
  the subprocess can never block on a TTY or emit ANSI into the JSON.
- Degrades, never raises, for the expected cases: gh missing, signed out, no
  GitHub remote, network failure — each maps to a status + message the offline
  cockpit renders without breaking.

Note the deliberate wording throughout this module: the repo-wide invariant
scans in test_git_readonly.py ban quoted git / mutation argv tokens outside
git_service, and this file must stay clean of them.
"""
import json
import os
import subprocess
import time
from typing import Optional

from app.core.utils import now_utc
from app.schemas.git import GitPrSummary, GitPullRequest

_TIMEOUT_S = 10  # network read — generous vs git_service's 5s local reads
_PR_TTL_S = 60.0  # ponytail: in-process TTL; a click within a minute is free

_PR_LIMIT = "20"
_PR_FIELDS = (
    "number,title,state,isDraft,headRefName,baseRefName,url,author,"
    "updatedAt,reviewDecision"
)

_GH_BIN = "gh"

# The complete command surface. NEVER add a mutating or open-ended command here
# (pr merge/close/create/comment, repo *, api, alias, extension, ...).
_ALLOWED_GH: dict[str, tuple[str, ...]] = {
    "auth_status": ("auth", "status"),
    "pr_list": (
        "pr", "list", "--state", "open", "--limit", _PR_LIMIT,
        "--json", _PR_FIELDS,
    ),
}

_ENV = {
    **os.environ,
    "GH_PROMPT_DISABLED": "1",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "NO_COLOR": "1",
    "GH_PAGER": "cat",
    # gh resolves the repo through internal Git reads; keep optional locks off
    # so those reads never write the index (same hardening as git_service).
    "GIT_OPTIONAL_LOCKS": "0",
}


def _run_gh(repo_path: str, argv: tuple[str, ...]) -> tuple[int, str, str]:
    """Run one exact allowlisted gh command with ``repo_path`` as cwd (gh
    resolves owner/repo from the folder's own remotes). Returns
    ``(returncode, stdout, stderr)``. Raises ``ValueError`` for any argv not in
    the allowlist, ``FileNotFoundError`` when gh is absent, and
    ``subprocess.TimeoutExpired`` on timeout — handled by ``_summary``."""
    if argv not in _ALLOWED_GH.values():
        raise ValueError(f"refusing non-allowlisted gh argv: {argv!r}")
    proc = subprocess.run(
        [_GH_BIN, *argv],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        env=_ENV,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _parse_prs(out: str) -> list[GitPullRequest]:
    rows = json.loads(out or "[]")
    prs: list[GitPullRequest] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prs.append(
            GitPullRequest(
                number=int(row.get("number", 0)),
                title=str(row.get("title", "")),
                state=str(row.get("state", "")),
                is_draft=bool(row.get("isDraft", False)),
                head=row.get("headRefName") or None,
                base=row.get("baseRefName") or None,
                url=row.get("url") or None,
                author=(row.get("author") or {}).get("login") or None,
                updated_at=row.get("updatedAt") or None,
                review_decision=row.get("reviewDecision") or None,
            )
        )
    return prs


def _summary(project_id: str, folder_path: Optional[str]) -> GitPrSummary:
    """Build the PR summary. Never raises for the expected cases — every
    failure mode maps to a ``status`` + ``message`` on a valid 200 body."""
    s = GitPrSummary(project_id=project_id, checked_at=now_utc())

    if not folder_path or not os.path.isdir(folder_path):
        s.message = "Project folder is missing or not on disk."
        return s

    try:
        rc, _, _err = _run_gh(folder_path, _ALLOWED_GH["auth_status"])
    except FileNotFoundError:
        s.status = "no_gh"
        s.message = "GitHub CLI (gh) is not installed or not on PATH."
        return s
    except (subprocess.TimeoutExpired, OSError):
        s.message = "gh timed out."
        return s
    if rc != 0:
        s.status = "no_auth"
        s.message = (
            "gh is not signed in — run `gh auth login` in a terminal. "
            "Planarus never stores the credential."
        )
        return s
    s.authenticated = True

    try:
        rc, out, err = _run_gh(folder_path, _ALLOWED_GH["pr_list"])
    except (subprocess.TimeoutExpired, OSError):
        s.message = "gh timed out."
        return s
    if rc != 0:
        # Typically "no GitHub remote" / network problems. Truncate stderr —
        # never surface more than a short human hint.
        s.message = (err or "gh pr list returned non-zero.")[:300]
        return s

    try:
        s.prs = _parse_prs(out)
    except (ValueError, TypeError):
        s.message = "Could not parse gh output."
        return s

    s.status = "ok"
    return s


# ponytail: module-global TTL dict keyed by project id — right for a local
# single-process app; same shape as git_service's snapshot cache.
_pr_cache: dict[str, tuple[float, GitPrSummary]] = {}


def pr_summary(project_id: str, folder_path: Optional[str]) -> GitPrSummary:
    """TTL-cached read-only open-PR summary for the project's folder."""
    now = time.monotonic()
    hit = _pr_cache.get(project_id)
    if hit is not None and hit[0] > now:
        return hit[1]
    summary = _summary(project_id, folder_path)
    _pr_cache[project_id] = (now + _PR_TTL_S, summary)
    return summary
