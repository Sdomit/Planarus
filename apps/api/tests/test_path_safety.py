import os

import pytest
from app.fsmemory.path_safety import (
    PathSafetyError,
    is_reparse_point,
    resolve_root,
    resolve_within,
)


def test_resolve_within_ok(tmp_path):
    target = resolve_within(str(tmp_path), "context/NEXT_STEP.md")
    assert os.path.normcase(target).startswith(
        os.path.normcase(os.path.realpath(str(tmp_path)))
    )
    assert target.endswith("NEXT_STEP.md")


@pytest.mark.parametrize(
    "bad",
    [
        "../escape.md",
        "context/../../escape.md",
        "/etc/passwd",
        "C:/Windows/system32/x",
        "context/file:stream",  # NTFS alternate data stream
        "\\\\server\\share\\x",  # UNC
        "..",
        "./x",
        "",
    ],
)
def test_resolve_within_rejects(tmp_path, bad):
    with pytest.raises(PathSafetyError):
        resolve_within(str(tmp_path), bad)


def test_resolve_root_requires_absolute():
    with pytest.raises(PathSafetyError):
        resolve_root("relative/dir")


def test_is_reparse_point_false_for_plain_dir(tmp_path):
    assert is_reparse_point(str(tmp_path)) is False


def test_symlink_escape_denied(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret", encoding="utf-8")

    link = root / "context"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("cannot create a symlink on this OS without privilege")

    # A path that traverses the symlinked directory escapes the root and is denied.
    with pytest.raises(PathSafetyError):
        resolve_within(str(root), "context/secret.md")


def test_junction_escape_denied(tmp_path):
    if os.name != "nt":
        pytest.skip("junctions are Windows-only")
    import subprocess

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret", encoding="utf-8")

    link = root / "ctxjunction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip(f"could not create a junction: {result.stderr.strip()}")

    with pytest.raises(PathSafetyError):
        resolve_within(str(root), "ctxjunction/secret.md")
