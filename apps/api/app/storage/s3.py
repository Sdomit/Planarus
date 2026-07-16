"""S3-compatible object-storage backend (Phase 10.3b).

Implements the `Storage` protocol against any S3-compatible object store (AWS S3,
MinIO, R2, …) using boto3, imported lazily so the default install and the local/
memory backends never require it (the optional ``[s3]`` extra provides it).

Addressing mirrors the other backends: an object's key is ``{prefix}/{root}/{rel}``
(normalized, forward-slash), so the same ``(root, relative_path)`` a project uses
locally maps to a deterministic object key. Like the in-memory backend it enforces
its own key-safety (no ``..`` traversal, no absolute relative paths) since the
POSIX symlink/realpath model doesn't apply to a keyspace.

Object stores have no native append; ``append_line`` is a read-modify-write, which
is fine for the small append-only logs fsmemory writes but is not concurrency-safe
across writers (documented; a hosted deployment with concurrent writers would use
a different log sink).
"""
from __future__ import annotations

from typing import Optional

from app.storage.base import StorageError


def _boto3():
    try:
        import boto3  # lazy: only needed for the s3 backend
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise StorageError(
            "the s3 storage backend requires boto3 (install the [s3] extra)"
        ) from exc
    return boto3


def _safe_rel(relative_path: str) -> str:
    raw = relative_path.replace("\\", "/")
    if raw.startswith("/"):
        raise StorageError(f"relative_path must not be absolute: {relative_path!r}")
    rel = raw.strip("/")
    parts = rel.split("/")
    if not rel or any(p in ("", ".", "..") for p in parts):
        raise StorageError(f"unsafe relative path: {relative_path!r}")
    return rel


class S3Storage:
    """A `Storage` backed by an S3 bucket. Config comes from settings (bucket,
    optional key prefix, region, optional endpoint URL for S3-compatibles)."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        client=None,
    ) -> None:
        if not bucket:
            raise StorageError("s3 backend requires AGENTBOARD_S3_BUCKET")
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = client or _boto3().client(
            "s3", region_name=region, endpoint_url=endpoint_url or None
        )

    def _key(self, root: str, relative_path: str) -> str:
        rel = _safe_rel(relative_path)
        root_part = root.replace("\\", "/").strip("/")
        parts = [p for p in (self._prefix, root_part, rel) if p]
        return "/".join(parts)

    def _location(self, root: str, relative_path: str) -> str:
        return f"s3://{self._bucket}/{self._key(root, relative_path)}"

    def write_bytes(self, root: str, relative_path: str, data: bytes) -> str:
        self._client.put_object(
            Bucket=self._bucket, Key=self._key(root, relative_path), Body=bytes(data)
        )
        return self._location(root, relative_path)

    def read_bytes(self, root: str, relative_path: str) -> Optional[bytes]:
        try:
            resp = self._client.get_object(
                Bucket=self._bucket, Key=self._key(root, relative_path)
            )
        except Exception as exc:  # NoSuchKey / 404
            if _is_not_found(exc):
                return None
            raise
        return resp["Body"].read()

    def exists(self, root: str, relative_path: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket, Key=self._key(root, relative_path)
            )
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise

    def ensure_file(self, root: str, relative_path: str) -> str:
        if not self.exists(root, relative_path):
            self.write_bytes(root, relative_path, b"")
        return self._location(root, relative_path)

    def append_line(self, root: str, relative_path: str, line: str) -> str:
        existing = self.read_bytes(root, relative_path) or b""
        return self.write_bytes(root, relative_path, existing + line.encode("utf-8"))


def _is_not_found(exc: Exception) -> bool:
    """True for a boto3 missing-object error (get→NoSuchKey, head→404)."""
    resp = getattr(exc, "response", None)
    if not isinstance(resp, dict):
        return False
    return resp.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound")
