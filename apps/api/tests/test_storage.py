"""Phase 10.3 — pluggable storage backends.

Verifies the Storage protocol is honored by both shipped backends, that atomic_io
routes through the active backend (so nothing hits disk under the memory backend),
and that the memory backend enforces its own key-safety. The local backend's
byte-identical behavior is covered by the existing fsmemory suite.
"""
import pytest
from app.core.config import settings
from app.fsmemory import atomic_io
from app.storage import (
    InMemoryStorage,
    LocalFilesystemStorage,
    Storage,
    StorageError,
    get_storage,
    reset_storage,
)


@pytest.fixture(name="memory_backend")
def memory_backend_fixture(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "memory")
    reset_storage()
    yield get_storage()
    reset_storage()


def test_both_backends_satisfy_protocol():
    assert isinstance(LocalFilesystemStorage(), Storage)
    assert isinstance(InMemoryStorage(), Storage)


def test_get_storage_default_is_local():
    reset_storage()
    assert isinstance(get_storage(), LocalFilesystemStorage)


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "nope")
    reset_storage()
    with pytest.raises(StorageError):
        get_storage()
    reset_storage()


def test_memory_backend_roundtrip_via_atomic_io(memory_backend):
    # atomic_io must delegate — writes land in memory, never on disk.
    root = "/does/not/exist/on/disk"
    assert atomic_io.read_text(root, "context/A.md") is None
    atomic_io.write_text(root, "context/A.md", "hello\nworld\n")
    assert atomic_io.read_text(root, "context/A.md") == "hello\nworld\n"
    assert memory_backend.exists(root, "context/A.md")


def test_memory_backend_write_if_changed(memory_backend):
    root = "/virtual"
    assert atomic_io.write_text_if_changed(root, "x.md", "a") is True
    assert atomic_io.write_text_if_changed(root, "x.md", "a") is False
    assert atomic_io.write_text_if_changed(root, "x.md", "b") is True


def test_memory_backend_append_jsonl(memory_backend):
    root = "/virtual"
    atomic_io.append_jsonl(root, ".planarus/audit.jsonl", {"a": 1})
    atomic_io.append_jsonl(root, ".planarus/audit.jsonl", {"b": 2})
    lines = atomic_io.read_text(root, ".planarus/audit.jsonl").splitlines()
    assert len(lines) == 2


def test_memory_backend_ensure_file_no_truncate(memory_backend):
    root = "/virtual"
    atomic_io.write_text(root, "keep.md", "content")
    atomic_io.ensure_file(root, "keep.md")
    assert atomic_io.read_text(root, "keep.md") == "content"


def test_memory_backend_rejects_traversal(memory_backend):
    for bad in ("../escape.md", "a/../../b.md", "/abs/path.md"):
        with pytest.raises(StorageError):
            memory_backend.write_bytes("/virtual", bad, b"x")
