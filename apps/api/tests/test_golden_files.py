"""Golden-file tests for every `context/*` kind.

Run once with PLANARUS_UPDATE_GOLDEN=1 to (re)generate the fixtures under
tests/golden/, then commit them. Thereafter the test fails on any rendering
change, which is the point — generated output must be stable and reviewed.
"""
import os
from pathlib import Path

import pytest
from app.fsmemory.renderers import RenderContext, render
from app.fsmemory.spec import CONTEXT_FILES
from app.models.project import Project
from app.models.workspace import Workspace

GOLDEN_DIR = Path(__file__).parent / "golden"
FIXED_TS = "2026-06-19T00:00:00+00:00"


def _golden_context() -> RenderContext:
    ws = Workspace(
        id="ws_golden",
        name="Golden Workspace",
        slug="golden-ws",
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
    )
    proj = Project(
        id="proj_golden",
        workspace_id="ws_golden",
        title="Golden Project",
        slug="golden-project",
        summary="A deterministic project for golden tests.",
        project_type="app",
        status="planning",
        folder_path="/srv/golden",
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
    )
    return RenderContext(project=proj, workspace=ws, updated_at=FIXED_TS)


@pytest.mark.parametrize("spec", CONTEXT_FILES, ids=lambda s: s.filename)
def test_golden(spec):
    rendered = render(spec, _golden_context())
    assert rendered.endswith("\n")
    assert "\r" not in rendered

    golden_path = GOLDEN_DIR / spec.filename
    if os.environ.get("PLANARUS_UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(rendered.encode("utf-8"))
        return

    assert golden_path.exists(), f"missing golden for {spec.filename} (run with PLANARUS_UPDATE_GOLDEN=1)"
    expected = golden_path.read_bytes().decode("utf-8")
    assert rendered == expected, f"golden mismatch for {spec.filename}"
