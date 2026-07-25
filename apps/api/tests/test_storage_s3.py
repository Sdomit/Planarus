"""Phase 10.3b — S3 storage backend (against a mocked S3 via moto).

Skipped automatically if boto3/moto aren't installed (the [s3] extra). Verifies the
adapter satisfies the Storage protocol and behaves like the other backends:
write/read/exists/ensure/append round-trips, missing-object → None, key layout, and
traversal rejection.
"""
import pytest

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from app.storage import Storage, StorageError  # noqa: E402
from app.storage.s3 import S3Storage  # noqa: E402
from moto import mock_aws  # noqa: E402

BUCKET = "planarus-test"


@pytest.fixture(name="store")
def store_fixture(monkeypatch):
    for var, val in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(var, val)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3Storage(BUCKET, prefix="pfx", region="us-east-1", client=client)


def test_satisfies_protocol(store):
    assert isinstance(store, Storage)


def test_write_read_roundtrip_and_key_layout(store):
    loc = store.write_bytes("/proj/root", "context/A.md", b"hello")
    assert store.read_bytes("/proj/root", "context/A.md") == b"hello"
    # key = prefix / root / rel (root stripped of leading slash)
    assert loc == "s3://planarus-test/pfx/proj/root/context/A.md"


def test_missing_object_reads_none(store):
    assert store.read_bytes("/root", "nope.md") is None
    assert store.exists("/root", "nope.md") is False


def test_exists_after_write(store):
    store.write_bytes("/root", "x.md", b"1")
    assert store.exists("/root", "x.md") is True


def test_ensure_file_no_truncate(store):
    store.write_bytes("/root", "keep.md", b"content")
    store.ensure_file("/root", "keep.md")
    assert store.read_bytes("/root", "keep.md") == b"content"
    # ensure_file creates an empty object when absent
    store.ensure_file("/root", "new.md")
    assert store.read_bytes("/root", "new.md") == b""


def test_append_line_accumulates(store):
    store.append_line("/root", "log.jsonl", '{"a":1}\n')
    store.append_line("/root", "log.jsonl", '{"b":2}\n')
    assert store.read_bytes("/root", "log.jsonl").decode().count("\n") == 2


def test_rejects_traversal(store):
    for bad in ("../escape.md", "a/../../b.md", "/abs/path.md"):
        with pytest.raises(StorageError):
            store.write_bytes("/root", bad, b"x")


def test_missing_bucket_config_raises():
    with pytest.raises(StorageError):
        S3Storage("", client=object())
