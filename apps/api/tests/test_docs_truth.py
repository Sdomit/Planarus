"""Guards for the documentation invariants #100 was filed about.

The issue's real complaint was not that a few files were stale — it was that
nothing stopped them going stale.

Most of what this module used to check was structural policing of `docs/plan/`:
no two documents sharing a number prefix, every document reachable from the
index, every index link resolving. Those documents are no longer part of the
published repository, so there is no shared tree left to police and the checks
went with them.

What survives is the one invariant that was never about documentation prose at
all — three separate places claim to know the application's version, and they
have disagreed before.
"""
import tomllib
from pathlib import Path

from app.core.config import settings

REPO = Path(__file__).resolve().parents[3]


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
