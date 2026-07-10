"""Guards the Phase 8 exit criterion: no mutating Git path exists anywhere in the
codebase. Git may only be read."""
from pathlib import Path

from app.services import git_service

APP_DIR = Path(git_service.__file__).resolve().parents[1]  # app/
GIT_SERVICE = Path(git_service.__file__).resolve()

# Git verbs that change repo / index / worktree / refs / config. None of these
# may appear as a quoted argv token anywhere in app source.
MUTATING_VERBS = (
    "commit", "push", "checkout", "reset", "merge", "rebase", "pull", "fetch",
    "clone", "add", "rm", "mv", "stash", "cherry-pick", "revert", "tag", "init",
    "apply", "am", "restore", "switch", "gc", "prune", "update-ref",
    "symbolic-ref", "worktree", "submodule", "notes", "filter-branch",
    "sparse-checkout", "config",
)

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


def test_run_rejects_mutating_verb_at_call_time(tmp_path) -> None:
    """The verb guard lives inside _run, so it fires for ANY caller (including a
    future module that imports _run directly) — before git is ever invoked."""
    import pytest

    for verb in ("push", "commit", "checkout", "reset"):
        with pytest.raises(ValueError):
            git_service._run(str(tmp_path), (verb, "whatever"))
