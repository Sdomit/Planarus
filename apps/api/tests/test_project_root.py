"""Unit tests for the managed-project-root chokepoint (issue #115, slice 115.0)."""
import os
import types

import pytest

from app.core.config import settings
from app.fsmemory.path_safety import PathSafetyError
from app.fsmemory.project_root import (
    ProjectRootError,
    assert_not_dangerous,
    managed_base,
    managed_root_for,
    resolve_project_root,
    roots_overlap,
    validate_local_root,
)


def _proj(workspace_id="ws_1", project_id="proj_1", folder_path=None):
    return types.SimpleNamespace(
        id=project_id, workspace_id=workspace_id, folder_path=folder_path
    )


def test_roots_overlap_equal_and_contained(tmp_path):
    a = str(tmp_path / "x")
    os.makedirs(a)
    assert roots_overlap(a, a)
    assert roots_overlap(a, os.path.join(a, "sub"))
    assert roots_overlap(os.path.join(a, "sub"), a)


def test_roots_overlap_siblings_do_not(tmp_path):
    os.makedirs(tmp_path / "x")
    os.makedirs(tmp_path / "x2")
    assert not roots_overlap(str(tmp_path / "x"), str(tmp_path / "x2"))


def test_assert_not_dangerous_rejects_system_dir():
    # Raw denylist match (normcase-equal on POSIX and Windows alike).
    with pytest.raises(ProjectRootError):
        assert_not_dangerous("/etc")


def test_assert_not_dangerous_rejects_filesystem_root():
    root = os.path.abspath(os.sep)  # "/" on POSIX, e.g. "C:\\" on Windows
    with pytest.raises(ProjectRootError):
        assert_not_dangerous(root)


def test_assert_not_dangerous_allows_tmp(tmp_path):
    assert_not_dangerous(os.path.realpath(str(tmp_path / "proj")))  # no raise


def test_managed_root_for_derives_under_base(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path))
    base = os.path.realpath(str(tmp_path))
    assert managed_root_for("ws_1", "proj_1") == os.path.join(base, "ws_1", "proj_1")


def test_managed_root_for_requires_base(monkeypatch):
    monkeypatch.setattr(settings, "projects_root", "")
    with pytest.raises(ProjectRootError):
        managed_root_for("ws_1", "proj_1")


def test_managed_root_for_rejects_unsafe_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "projects_root", str(tmp_path))
    for bad in ("../escape", "a/b", "a\\b", "..", ""):
        with pytest.raises(ProjectRootError):
            managed_root_for("ws_1", bad)


def test_validate_local_root_rejects_relative():
    with pytest.raises(PathSafetyError):
        validate_local_root("relative/path")


def test_resolve_project_root_auth_ignores_stored_and_derives(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "projects_root", str(tmp_path))
    base = os.path.realpath(str(tmp_path))
    # A tampered stored folder_path is IGNORED in auth mode — the id-derived path wins.
    p = _proj(folder_path=os.path.abspath(os.sep))
    assert resolve_project_root(p) == os.path.join(base, "ws_1", "proj_1")


def test_resolve_project_root_local_uses_validated_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    d = str(tmp_path / "myproj")
    os.makedirs(d)
    p = _proj(folder_path=d)
    assert resolve_project_root(p) == os.path.realpath(d)


def test_resolve_project_root_local_rejects_dangerous(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    p = _proj(folder_path=os.path.abspath(os.sep))  # filesystem/drive root
    with pytest.raises(ProjectRootError):
        resolve_project_root(p)


def test_resolve_project_root_local_missing_folder_raises(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    with pytest.raises(ProjectRootError):
        resolve_project_root(_proj(folder_path=None))
