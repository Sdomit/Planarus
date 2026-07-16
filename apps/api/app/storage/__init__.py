"""Pluggable storage backend for generated project artifacts (Phase 10.3).

The fsmemory layer writes derived Markdown/JSONL through a narrow set of
primitives (write/read bytes, append a line, existence). Historically those went
straight to the local filesystem via ``atomic_io``. This package puts a ``Storage``
protocol behind that choke point so a hosted deployment can swap in object storage
(S3/GCS) without touching callers.

**Default is the local filesystem** (`AGENTBOARD_STORAGE_BACKEND=local`), byte-for-
byte identical to the previous behavior. The in-memory backend is for tests and
ephemeral/hosted-preview use; a real S3 adapter is a bounded future addition
(P10.3b) that implements the same protocol.
"""
from __future__ import annotations

from app.core.config import settings
from app.storage.base import Storage, StorageError
from app.storage.local import LocalFilesystemStorage
from app.storage.memory import InMemoryStorage

__all__ = [
    "Storage",
    "StorageError",
    "LocalFilesystemStorage",
    "InMemoryStorage",
    "get_storage",
    "reset_storage",
]

_BACKENDS = {
    "local": LocalFilesystemStorage,
    "memory": InMemoryStorage,
}

_cache: dict[str, Storage] = {}


def get_storage() -> Storage:
    """Return the active storage backend (cached per backend name).

    Reads ``settings.storage_backend`` each call, so a monkeypatched setting takes
    effect immediately in tests. Unknown backend names fail loudly at first use.
    """
    name = settings.storage_backend
    if name not in _cache:
        if name == "s3":
            from app.storage.s3 import S3Storage  # lazy: boto3 only if selected

            _cache[name] = S3Storage(
                bucket=settings.storage_s3_bucket,
                prefix=settings.storage_s3_prefix,
                region=settings.storage_s3_region or None,
                endpoint_url=settings.storage_s3_endpoint_url or None,
            )
        elif name in _BACKENDS:
            _cache[name] = _BACKENDS[name]()
        else:
            raise StorageError(
                f"unknown storage backend {name!r}; expected one of "
                f"{', '.join(sorted(_BACKENDS))}, s3"
            )
    return _cache[name]


def reset_storage() -> None:
    """Drop cached backend instances (clears in-memory state). Test helper."""
    _cache.clear()
