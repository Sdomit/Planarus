import pytest

from app.fsmemory import atomic_io
from app.fsmemory.path_safety import PathSafetyError, safe_makedirs
from app.storage import local as local_backend


def test_write_and_read_roundtrip(tmp_path):
    root = str(tmp_path)
    atomic_io.write_text(root, "context/A.md", "hello\nworld\n")
    assert atomic_io.read_text(root, "context/A.md") == "hello\nworld\n"


def test_write_forces_lf(tmp_path):
    root = str(tmp_path)
    atomic_io.write_text(root, "context/A.md", "a\r\nb\r\n")
    data = atomic_io.read_bytes(root, "context/A.md")
    assert data == b"a\nb\n"
    assert b"\r\n" not in data


def test_write_if_changed(tmp_path):
    root = str(tmp_path)
    assert atomic_io.write_text_if_changed(root, "x.txt", "v1") is True
    assert atomic_io.write_text_if_changed(root, "x.txt", "v1") is False
    assert atomic_io.write_text_if_changed(root, "x.txt", "v2") is True


def test_read_missing_returns_none(tmp_path):
    assert atomic_io.read_text(str(tmp_path), "context/missing.md") is None


def test_no_temp_files_left(tmp_path):
    atomic_io.write_text(str(tmp_path), "context/A.md", "data")
    leftover = [p.name for p in (tmp_path / "context").iterdir() if p.name.startswith(".tmp-")]
    assert leftover == []


def test_rejects_escape(tmp_path):
    with pytest.raises(PathSafetyError):
        atomic_io.write_text(str(tmp_path), "../escape.md", "x")


def test_temp_cleanup_on_replace_failure(tmp_path, monkeypatch):
    # The atomic temp+replace behavior now lives in the local storage backend
    # (P10.3); atomic_io.write_bytes delegates to it. Patch os.replace there.
    root = str(tmp_path)
    safe_makedirs(root, "context")

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(local_backend.os, "replace", boom)
    with pytest.raises(RuntimeError):
        atomic_io.write_bytes(root, "context/A.md", b"data")

    leftover = [p.name for p in (tmp_path / "context").iterdir() if p.name.startswith(".tmp-")]
    assert leftover == []


def test_append_jsonl(tmp_path):
    root = str(tmp_path)
    atomic_io.append_jsonl(root, ".agentboard/audit-log.jsonl", {"a": 1})
    atomic_io.append_jsonl(root, ".agentboard/audit-log.jsonl", {"b": 2})
    lines = atomic_io.read_text(root, ".agentboard/audit-log.jsonl").splitlines()
    assert len(lines) == 2
