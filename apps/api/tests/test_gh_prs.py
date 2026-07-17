"""Phase 12c — read-only PR layer via the GitHub CLI.

Guards the gh chokepoint the same way test_git_readonly guards git: exact-argv
allowlist (refused by value, not just by verb), gh invoked from gh_service
only, zero stored tokens, and every failure mode degrading to a status +
message instead of an exception."""
import json
import subprocess
from pathlib import Path

import pytest

from app.schemas.git import GitPrSummary
from app.services import gh_service

APP_DIR = Path(gh_service.__file__).resolve().parents[1]  # app/
GH_SERVICE = Path(gh_service.__file__).resolve()

# --- allowlist gate -----------------------------------------------------------


def test_run_gh_refuses_anything_not_in_the_table(tmp_path) -> None:
    """The gate is exact-argv: even a read-looking variation is refused, and so
    is every mutating or open-ended gh surface."""
    refused = [
        ("pr", "merge", "1"),
        ("pr", "close", "1"),
        ("pr", "create"),
        ("pr", "comment", "1"),
        ("pr", "checkout", "1"),
        ("repo", "clone", "x/y"),
        ("api", "repos/x/y"),
        ("alias", "set", "x", "y"),
        ("extension", "install", "x"),
        ("auth", "login"),
        ("auth", "token"),
        # allowlisted command with one extra/changed token → still refused
        ("pr", "list"),
        ("auth", "status", "--show-token"),
    ]
    for argv in refused:
        with pytest.raises(ValueError):
            gh_service._run_gh(str(tmp_path), argv)


def test_allowlist_is_read_only_and_closed() -> None:
    allowed = set(gh_service._ALLOWED_GH.values())
    assert allowed == {
        ("auth", "status"),
        (
            "pr", "list", "--state", "open", "--limit", gh_service._PR_LIMIT,
            "--json", gh_service._PR_FIELDS,
        ),
    }
    # Nothing that can write or execute arbitrary API calls may ever appear.
    banned_tokens = {"merge", "close", "create", "comment", "edit", "checkout",
                     "clone", "api", "alias", "extension", "login", "token"}
    for argv in allowed:
        assert banned_tokens.isdisjoint(argv), argv


def test_only_gh_service_shells_to_gh() -> None:
    """gh_service is the single chokepoint that invokes the gh binary (the same
    scan shape test_git_readonly uses for git)."""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        if "__pycache__" in path.parts or path == GH_SERVICE:
            continue
        src = path.read_text(encoding="utf-8")
        shells = any(
            tok in src
            for tok in ("subprocess", "Popen", "os.system", "os.exec", "os.spawn")
        )
        if shells and ('"gh"' in src or "'gh'" in src):
            offenders.append(str(path.relative_to(APP_DIR)))
    assert offenders == [], f"unexpected gh subprocess call(s): {offenders}"


# --- summary flow (no real gh: the runner is monkeypatched) -------------------


PR_ROW = {
    "number": 7, "title": "Add PR layer", "state": "OPEN", "isDraft": False,
    "headRefName": "feat/x", "baseRefName": "main",
    "url": "https://github.com/x/y/pull/7",
    "author": {"login": "sdomit"}, "updatedAt": "2026-07-17T12:00:00Z",
    "reviewDecision": "",
}


def _patch_runner(monkeypatch, responses: dict[tuple[str, ...], tuple[int, str, str]]):
    def fake(_repo: str, argv: tuple[str, ...]):
        assert argv in gh_service._ALLOWED_GH.values(), argv
        return responses[argv]
    monkeypatch.setattr(gh_service, "_run_gh", fake)


@pytest.fixture(autouse=True)
def _no_pr_cache(monkeypatch):
    monkeypatch.setattr(gh_service, "_pr_cache", {})


def test_summary_ok_parses_and_flattens(tmp_path, monkeypatch) -> None:
    _patch_runner(monkeypatch, {
        gh_service._ALLOWED_GH["auth_status"]: (0, "ok", ""),
        gh_service._ALLOWED_GH["pr_list"]: (0, json.dumps([PR_ROW]), ""),
    })
    s = gh_service._summary("p1", str(tmp_path))
    assert s.status == "ok" and s.authenticated is True
    assert len(s.prs) == 1
    pr = s.prs[0]
    assert (pr.number, pr.head, pr.base, pr.author) == (7, "feat/x", "main", "sdomit")
    assert pr.review_decision is None  # empty string flattens to None


def test_summary_no_gh(tmp_path, monkeypatch) -> None:
    def raise_missing(_repo, _argv):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(gh_service, "_run_gh", raise_missing)
    s = gh_service._summary("p1", str(tmp_path))
    assert s.status == "no_gh" and "not installed" in (s.message or "")


def test_summary_no_auth_never_leaks_a_token_hint(tmp_path, monkeypatch) -> None:
    _patch_runner(monkeypatch, {
        gh_service._ALLOWED_GH["auth_status"]: (1, "", "You are not logged in"),
    })
    s = gh_service._summary("p1", str(tmp_path))
    assert s.status == "no_auth"
    assert "never stores the credential" in (s.message or "")


def test_summary_failed_truncates_stderr(tmp_path, monkeypatch) -> None:
    _patch_runner(monkeypatch, {
        gh_service._ALLOWED_GH["auth_status"]: (0, "ok", ""),
        gh_service._ALLOWED_GH["pr_list"]: (1, "", "boom " * 200),
    })
    s = gh_service._summary("p1", str(tmp_path))
    assert s.status == "failed" and len(s.message or "") <= 300


def test_summary_missing_folder() -> None:
    s = gh_service._summary("p1", None)
    assert s.status == "failed" and "folder" in (s.message or "").lower()


def test_summary_timeout(tmp_path, monkeypatch) -> None:
    def raise_timeout(_repo, _argv):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=1)
    monkeypatch.setattr(gh_service, "_run_gh", raise_timeout)
    s = gh_service._summary("p1", str(tmp_path))
    assert s.status == "failed" and "timed out" in (s.message or "")


def test_pr_summary_ttl_cache(tmp_path, monkeypatch) -> None:
    calls = {"n": 0}

    def fake(_repo, argv):
        calls["n"] += 1
        if argv == gh_service._ALLOWED_GH["auth_status"]:
            return (0, "ok", "")
        return (0, "[]", "")

    monkeypatch.setattr(gh_service, "_run_gh", fake)
    first = gh_service.pr_summary("p1", str(tmp_path))
    second = gh_service.pr_summary("p1", str(tmp_path))
    assert first is second  # cache hit — no second gh invocation
    assert calls["n"] == 2  # auth_status + pr_list, exactly once


# --- endpoint -----------------------------------------------------------------


def test_prs_endpoint_shape_and_degrade(client, monkeypatch) -> None:
    """Unknown project → 404; known project without gh → 200 degrade body."""
    assert client.get("/api/v1/projects/nope/git/prs").status_code == 404

    ws = client.post("/api/v1/workspaces", json={"name": "gh-ws", "slug": "gh-ws"}).json()
    res = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "GH Proj", "slug": "gh-proj"},
    )
    assert res.status_code == 201, res.text
    proj = res.json()

    monkeypatch.setattr(
        gh_service, "pr_summary",
        lambda pid, _path: GitPrSummary(
            project_id=pid, status="no_gh",
            message="GitHub CLI (gh) is not installed or not on PATH.",
            checked_at="t",
        ),
    )
    res = client.get(f"/api/v1/projects/{proj['id']}/git/prs")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "no_gh" and body["prs"] == []
    assert body["authenticated"] is False
