"""Guards the near-total no-mutation rule for Git (Phase 8), plus its ONE
documented exception — the Phase 12b explicit fetch.

The invariant is unchanged for everything except a human-clicked, gated fetch of
remote-tracking refs: no commit/push/checkout/reset/merge/pull/… path exists
anywhere in app source, and the read-only `_run` gate still refuses `fetch`
itself. The single blessed mutation lives in the separate `_run_fetch` path and
is exercised by test_git_fetch.py."""
from pathlib import Path

import pytest

from app.services import git_service

APP_DIR = Path(git_service.__file__).resolve().parents[1]  # app/
GIT_SERVICE = Path(git_service.__file__).resolve()

# Git verbs that change repo / index / worktree / refs / config. None of these
# may appear as a quoted argv token anywhere in app source.
#
# Phase 12b exception: `fetch` (with `--prune`) is the sole allowed mutation, and
# only inside git_service's dedicated `_run_fetch` path. It is intentionally
# absent from this set so every OTHER mutating verb stays banned everywhere.
MUTATING_VERBS = (
    "commit", "push", "checkout", "reset", "merge", "rebase", "pull",
    "clone", "add", "rm", "mv", "stash", "cherry-pick", "revert", "tag", "init",
    "apply", "am", "restore", "switch", "gc", "prune", "update-ref",
    "symbolic-ref", "worktree", "submodule", "notes", "filter-branch",
    "sparse-checkout", "config",
)

# The one blessed mutation, allowed to appear ONLY in git_service (the fetch path).
FETCH_ONLY_VERBS = ("fetch",)

_SUBPROCESS_TOKENS = (
    "subprocess", "Popen", "os.system", "os.exec", "os.spawn", "os.popen",
    "create_subprocess",
)
_GIT_TOKENS = ('"git"', "'git'")


def _app_py_files() -> list[Path]:
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_allowlist_only_read_only_verbs() -> None:
    for key, argv in git_service._READ_ONLY_GIT.items():
        assert argv[0] in git_service._READ_ONLY_VERBS, key
    # The read-only verb set itself must not overlap the mutating set.
    assert git_service._READ_ONLY_VERBS.isdisjoint(MUTATING_VERBS)
    # The read-only gate must NEVER learn to fetch: fetch stays out of the
    # allowlisted verbs and out of the read-command table (Phase 12b invariant).
    assert "fetch" not in git_service._READ_ONLY_VERBS
    assert all(
        argv[0] != "fetch" for argv in git_service._READ_ONLY_GIT.values()
    )


def test_only_git_service_shells_to_git() -> None:
    """git_service is the single chokepoint that invokes the git binary."""
    offenders = []
    for path in _app_py_files():
        src = path.read_text(encoding="utf-8")
        shells = any(tok in src for tok in _SUBPROCESS_TOKENS)
        touches_git = any(tok in src for tok in _GIT_TOKENS)
        if shells and touches_git and path != GIT_SERVICE:
            offenders.append(str(path.relative_to(APP_DIR)))
    assert offenders == [], f"unexpected git subprocess call(s): {offenders}"


def test_git_service_has_no_mutating_argv() -> None:
    src = GIT_SERVICE.read_text(encoding="utf-8")
    present = [v for v in MUTATING_VERBS if f'"{v}"' in src or f"'{v}'" in src]
    assert present == [], f"mutating git verb(s) in argv: {present}"


def test_fetch_is_the_only_mutation_and_only_in_git_service() -> None:
    """The blessed fetch verb may appear ONLY in git_service — nowhere else in
    app source may an argv shell out `git fetch`."""
    for verb in FETCH_ONLY_VERBS:
        assert f'"{verb}"' in GIT_SERVICE.read_text(encoding="utf-8"), verb
    offenders = []
    for path in _app_py_files():
        if path == GIT_SERVICE:
            continue
        src = path.read_text(encoding="utf-8")
        if any(f'"{v}"' in src or f"'{v}'" in src for v in FETCH_ONLY_VERBS):
            offenders.append(str(path.relative_to(APP_DIR)))
    assert offenders == [], f"git fetch argv outside git_service: {offenders}"


def test_run_rejects_mutating_verb_at_call_time(tmp_path) -> None:
    """The verb guard lives inside _run, so it fires for ANY caller (including a
    future module that imports _run directly) — before git is ever invoked.
    `fetch` is included: the read-only gate refuses it, so the Phase 12b fetch
    must go through the separate `_run_fetch` path, never `_run`."""
    for verb in ("push", "commit", "checkout", "reset", "fetch"):
        with pytest.raises(ValueError):
            git_service._run(str(tmp_path), (verb, "whatever"))
