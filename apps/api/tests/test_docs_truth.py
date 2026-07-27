"""Guards for the documentation invariants #100 was filed about.

The issue's real complaint was not that a few files were stale — it was that
nothing stopped them going stale.

Most of what this module used to check was structural policing of `docs/plan/`:
no two documents sharing a number prefix, every document reachable from the
index, every index link resolving. Those documents are no longer part of the
published repository, so there is no shared tree left to police and the checks
went with them.

Two invariants survive, neither of them about documentation prose:

* four separate manifests claim to know the application's version, and they
  have disagreed before;
* every relative link in a published Markdown file must resolve, because this
  repository deliberately withholds part of its own documentation tree and a
  link into the withheld part is a 404 for every reader who is not the author.

The link check asks Git what ships, not the filesystem. That distinction is the
whole point of it: the manual check run before publication resolved paths on
disk, where `docs/plan/`, `context/` and `docs/dev/phase-*.md` were still
sitting untracked and gitignored, so seven dead links passed it and reached
readers anyway. A maintainer's working tree is not what a visitor clones.
"""
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from app.core.config import settings

REPO = Path(__file__).resolve().parents[3]


def test_version_single_source():
    """`/info`, the OpenAPI document and every package manifest report one version.

    They did not: `Settings.app_version` said 0.1.0 while `main.py` hardcoded
    0.2.0 into the OpenAPI document and `pyproject.toml` said 0.2.0 (#100). The
    npm manifests then drifted the same way — 0.1.0 against the API's 0.2.0 —
    because nothing here was checking them.
    """
    pyproject = tomllib.loads(
        (REPO / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert settings.app_version == pyproject["project"]["version"], (
        "Settings.app_version and apps/api/pyproject.toml disagree — the API "
        "would report a different version than it ships as"
    )

    from app.main import create_app

    assert create_app().version == settings.app_version, (
        "the OpenAPI document's version is not Settings.app_version"
    )

    for manifest in (REPO / "package.json", REPO / "apps" / "web" / "package.json"):
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
        assert version == settings.app_version, (
            f"{manifest.relative_to(REPO).as_posix()} says {version}, the API "
            f"says {settings.app_version} — a release would ship two numbers"
        )


# `[text](target)`, which also catches the `![alt](src)` image form.
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def _tracked() -> set[Path]:
    """Every path Git ships, plus the directories they live in.

    Directories matter because a link may legitimately point at one
    (`[the contracts](../api/)`), and Git only lists files.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    paths = {REPO}
    for name in listing.split("\0"):
        if not name:
            continue
        path = (REPO / name).resolve()
        paths.add(path)
        paths.update(p for p in path.parents if REPO in p.parents or p == REPO)
    return paths


def _strip_code_fences(text: str) -> str:
    """A link inside a fenced block is an example, not a link to follow."""
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        out.append("" if fenced else line)
    return "\n".join(out)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_relative_markdown_links_resolve():
    """No shipped document links to something this repository does not ship.

    `docs/plan/`, `context/` and `docs/dev/phase-*.md` are maintainer-local and
    excluded from the published tree (docs/README.md, "What is not in this
    repo"). Guides written before that split pointed straight into them, so a
    reader following the link got a 404 on the very page that was meant to
    explain the feature — while the author, who still had those files on disk,
    saw nothing wrong.
    """
    tracked = _tracked()
    broken = []
    for path in sorted(p for p in tracked if p.suffix == ".md"):
        body = _strip_code_fences(path.read_text(encoding="utf-8"))
        for target in MARKDOWN_LINK.findall(body):
            # A title (`[a](b "t")`) is not part of the path; nor is a fragment,
            # and a bare `#anchor` or absolute URL is not ours to resolve.
            target = target.split()[0].split("#")[0] if target.split() else ""
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if (path.parent / target).resolve() not in tracked:
                broken.append(f"{path.relative_to(REPO).as_posix()} -> {target}")

    assert not broken, (
        "Markdown links that point at something this repository does not "
        "ship:\n  " + "\n  ".join(broken)
    )
