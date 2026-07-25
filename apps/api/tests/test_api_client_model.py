"""Phase 7C1: ApiClient model — DB CHECK, unique key_id, secret-safe serializer."""
import uuid

import pytest
from app.core.utils import new_id, now_utc, now_utc_plus_hours
from app.models.api_client import ApiClient
from app.services.api_client_service import to_read
from sqlalchemy.exc import IntegrityError


def _ws(client) -> str:
    return client.post(
        "/api/v1/workspaces", json={"name": "W", "slug": f"w-{uuid.uuid4().hex[:8]}"}
    ).json()["id"]


def _row(ws_id, **over) -> ApiClient:
    base = dict(
        id=new_id("apc"),
        workspace_id=ws_id,
        key_id=new_id("k"),
        secret_hash="$argon2id$dummy",
        label="l",
        can_read=True,
        can_propose=False,
        project_ids_json="[]",
        created_at=now_utc(),
        expires_at=now_utc_plus_hours(24),
    )
    base.update(over)
    return ApiClient(**base)


def test_at_least_one_permission_check_enforced(client, session):
    ws = _ws(client)
    session.add(_row(ws, can_read=False, can_propose=False))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_either_permission_alone_is_allowed(client, session):
    ws = _ws(client)
    session.add(_row(ws, can_read=True, can_propose=False))
    session.add(_row(ws, can_read=False, can_propose=True))
    session.commit()  # no error


def test_key_id_is_unique(client, session):
    ws = _ws(client)
    session.add(_row(ws, key_id="dup-key"))
    session.commit()
    session.add(_row(ws, key_id="dup-key"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_to_read_never_exposes_secret_hash(client, session):
    ws = _ws(client)
    row = _row(ws, project_ids_json='["p1","p2"]')
    session.add(row)
    session.commit()
    session.refresh(row)
    read = to_read(row)
    dumped = read.model_dump()
    assert "secret_hash" not in dumped
    assert not hasattr(read, "secret_hash")
    assert read.project_ids == ["p1", "p2"]
    assert read.key_id == row.key_id
