"""Guards the near-total no-mutation rule for Git (Phase 8), plus its documented
exceptions — the Phase 12b explicit fetch and the Phase 12d explicit
commit/merge.

The rule that has not moved: no push/checkout/reset/rebase/pull/rm/config-write
path exists anywhere in app source, and the read-only `_run` gate refuses every
mutating verb — including the blessed ones, which must go through their own
separate gates.

What Phase 12d widened, and the price it pays for it: `add`, `commit` and
`merge` are now reachable, but only from inside git_service's `_run_write`,
only behind `PLANARUS_GIT_WRITE_ENABLED` (off by default), only with the local
control token, and only with an audit event per attempt. Those gates are
exercised by test_git_write.py; what this file guards is that the *set* stays
exactly that small and stays confined to git_service.

Verbs are matched as quoted argv tokens, which is exact here: no app module
outside git_service contains a quoted "add"/"commit"/"merge"/"fetch"."""
from pathlib import Path

import pytest
from app.services import git_service

APP_DIR = Path(git_service.__file__).resolve().parents[1]  # app/
GIT_SERVICE = Path(git_service.__file__).resolve()

# Git verbs that change repo / index / worktree / refs / config and have NO
# blessed path. None of these may appear as a quoted argv token anywhere in app
# source, git_service included. Shrinking this tuple is how a new mutation gets
# allowed, so it should be a deliberate, reviewed edit — never a quick fix for a
# red test.
MUTATING_VERBS = (
    "push", "checkout", "reset", "rebase", "pull",
    "clone", "rm", "mv", "stash", "cherry-pick", "revert", "tag", "init",
    "apply", "am", "restore", "switch", "gc", "prune", "update-ref",
    "symbolic-ref", "worktree", "submodule", "notes", "filter-branch",
    "sparse-checkout", "config",
)

# The blessed mutations, allowed to appear ONLY in git_service, each behind its
# own off-by-default env flag, the local control token and an audit event:
#   fetch          Phase 12b — remote-tracking refs only, never the worktree
#   add/commit/merge  Phase 12d — worktree and local history
FETCH_ONLY_VERBS = ("fetch",)
WRITE_ONLY_VERBS = ("add", "commit", "merge")
GIT_SERVICE_ONLY_VERBS = FETCH_ONLY_VERBS + WRITE_ONLY_VERBS

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


def test_blessed_mutations_appear_only_in_git_service() -> None:
    """fetch, add, commit and merge may appear ONLY in git_service — nowhere
    else in app source may an argv shell out a mutating git command."""
    src = GIT_SERVICE.read_text(encoding="utf-8")
    for verb in GIT_SERVICE_ONLY_VERBS:
        assert f'"{verb}"' in src, verb
    offenders = []
    for path in _app_py_files():
        if path == GIT_SERVICE:
            continue
        text = path.read_text(encoding="utf-8")
        present = [
            v
            for v in GIT_SERVICE_ONLY_VERBS
            if f'"{v}"' in text or f"'{v}'" in text
        ]
        if present:
            offenders.append(f"{path.relative_to(APP_DIR)}: {present}")
    assert offenders == [], f"mutating git argv outside git_service: {offenders}"


def test_write_allowlist_is_exactly_the_phase_12d_set() -> None:
    """The write gate may not quietly grow. Anything added here is a new way for
    the app to change a user's repository, so it has to be an explicit edit."""
    assert git_service._WRITE_VERBS == frozenset(WRITE_ONLY_VERBS)
    # The two gates stay disjoint: a read verb can never mutate, and a write
    # verb can never slip through the read path (which is the wider surface —
    # it backs every unauthenticated cockpit read).
    assert git_service._WRITE_VERBS.isdisjoint(git_service._READ_ONLY_VERBS)
    # And nothing in the never-blessed set is reachable through either gate.
    assert git_service._WRITE_VERBS.isdisjoint(MUTATING_VERBS)
    assert "fetch" not in git_service._WRITE_VERBS


def test_writes_are_off_by_default() -> None:
    """Cloning the repo and running it must not give the app write access to
    any repository. Both gates default off, and independently of each other."""
    from app.core.config import Settings

    fresh = Settings(_env_file=None)
    assert fresh.git_write_enabled is False
    assert fresh.git_fetch_enabled is False


def test_run_rejects_mutating_verb_at_call_time(tmp_path) -> None:
    """The verb guard lives inside _run, so it fires for ANY caller (including a
    future module that imports _run directly) — before git is ever invoked.
    `fetch` is included: the read-only gate refuses it, so the Phase 12b fetch
    must go through the separate `_run_fetch` path, never `_run`."""
    for verb in ("push", "commit", "checkout", "reset", "fetch"):
        with pytest.raises(ValueError):
            git_service._run(str(tmp_path), (verb, "whatever"))
