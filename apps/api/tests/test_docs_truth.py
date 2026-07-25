"""Guards for the documentation invariants #100 was filed about.

The issue's real complaint was not that a few files were stale — it was that
nothing stopped them going stale. In a repo whose operating model is "agents read
docs first", a colliding filename or a dead index link sends the next session to
the wrong document, and nothing fails until a human notices.

These are cheap structural checks, not prose review. They cannot tell you a
document is wrong; they can tell you it is unreachable, ambiguous, or
contradicted by the code.
"""
import re
import tomllib
from pathlib import Path

from app.core.config import settings

REPO = Path(__file__).resolve().parents[3]
PLAN = REPO / "docs" / "plan"
OVERVIEW = PLAN / "00-OVERVIEW.md"

_LINK = re.compile(r"\[[^\]]+\]\((?!https?://)([^)#]+\.md)(?:#[^)]*)?\)")


def test_no_two_plan_docs_share_a_number():
    """`20-cosmo-brand-theme.md` and `20-entity-attachments.md` both existed, so
    "read the Phase 20 plan doc" had two answers (#100)."""
    by_number: dict[str, list[str]] = {}
    for path in PLAN.glob("*.md"):
        number = path.name.split("-", 1)[0]
        by_number.setdefault(number, []).append(path.name)
    collisions = {n: sorted(f) for n, f in by_number.items() if len(f) > 1}
    assert not collisions, f"plan documents share a number prefix: {collisions}"


def test_every_overview_link_resolves():
    """The index linked `18-browser-extension.md` for months after that plan
    stopped existing on main (#100)."""
    text = OVERVIEW.read_text(encoding="utf-8")
    missing = sorted(
        target for target in _LINK.findall(text)
        if not (OVERVIEW.parent / target).resolve().exists()
    )
    assert not missing, f"00-OVERVIEW.md links to files that do not exist: {missing}"


def test_every_plan_doc_is_indexed():
    """A plan document nobody links to is a document nobody reads."""
    text = OVERVIEW.read_text(encoding="utf-8")
    linked = {Path(t).name for t in _LINK.findall(text)}
    unindexed = sorted(
        p.name for p in PLAN.glob("*.md")
        if p.name != "00-OVERVIEW.md" and p.name not in linked
    )
    assert not unindexed, f"plan documents missing from the index: {unindexed}"


def test_plan_doc_heading_matches_its_filename():
    """The number on the page is the number in the filename — otherwise a doc
    cites itself as something else, which is how the drift started.

    Only files 11 and up. `01`–`10` carry the *deliverable* numbers of the
    original plan, which do not line up one-to-one with files (`01-product-and-
    scope.md` is deliverables 1 and 2, so everything after it is offset). That
    offset is deliberate and recorded in the index; renumbering those headings
    would break every citation of the original deliverable numbers.
    """
    wrong = {}
    for path in sorted(PLAN.glob("*.md")):
        number_prefix = path.name.split("-", 1)[0]
        if path.name == "00-OVERVIEW.md" or not number_prefix.isdigit():
            continue
        if int(number_prefix) < 11:
            continue
        heading = next(
            (ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.startswith("# ")), "")
        match = re.match(r"# (\d+)\.", heading)
        if match and match.group(1) != path.name.split("-", 1)[0]:
            wrong[path.name] = heading.strip()
    assert not wrong, f"heading number disagrees with the filename: {wrong}"


def test_version_single_source():
    """`/info`, the OpenAPI document and the package manifest report one version.

    They did not: `Settings.app_version` said 0.1.0 while `main.py` hardcoded
    0.2.0 into the OpenAPI document and `pyproject.toml` said 0.2.0 (#100).
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
