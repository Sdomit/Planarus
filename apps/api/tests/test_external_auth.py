"""Phase 7C1: external API-key authentication edge cases."""
from types import SimpleNamespace

import pytest
from app.models.api_client import ApiClient
from sqlmodel import select

from tests.external_util import auth, issue_key, seed

PROJECTS = "/api/external/v1/projects"
_PAST = "2000-01-01T00:00:00+00:00"


@pytest.fixture
def env(client, external_api, session):
    ws, proj = seed(client, "auth")
    cm, raw = issue_key(client, ws, [proj], can_read=True)
    row = session.exec(select(ApiClient).where(ApiClient.key_id == cm["key_id"])).one()
    return SimpleNamespace(ws=ws, proj=proj, key=raw, row=row, session=session)


def test_valid_key_succeeds(env, client):
    assert client.get(PROJECTS, headers=auth(env.key)).status_code == 200


def test_expired_key_rejected(env, client):
    env.row.expires_at = _PAST
    env.session.add(env.row)
    env.session.commit()
    assert client.get(PROJECTS, headers=auth(env.key)).status_code == 401


def test_disabled_key_rejected(env, client):
    env.row.enabled = False
    env.session.add(env.row)
    env.session.commit()
    assert client.get(PROJECTS, headers=auth(env.key)).status_code == 401


def test_revoked_key_rejected(env, client):
    from app.core.utils import now_utc

    env.row.revoked_at = now_utc()
    env.session.add(env.row)
    env.session.commit()
    assert client.get(PROJECTS, headers=auth(env.key)).status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Bearer ",
        "Bearer notakey",
        "Basic agbk_a_b",
        "Bearer agbk_unknownid_secret",  # well-formed but unknown key id
        "Bearer agbk_a",
    ],
)
def test_malformed_or_unknown_authorization_rejected(env, client, header):
    headers = {"Host": "127.0.0.1"}
    if header is not None:
        headers["Authorization"] = header
    res = client.get(PROJECTS, headers=headers)
    assert res.status_code == 401
    assert res.json()["type"].endswith("/unauthorized")


def test_wrong_secret_rejected(env, client):
    # Right key_id, wrong secret.
    bad = f"agbk_{env.row.key_id}_wrongsecretvalue"
    assert client.get(PROJECTS, headers=auth(bad)).status_code == 401


def test_last_used_at_updates_then_throttles(env, client):
    assert env.row.last_used_at is None
    client.get(PROJECTS, headers=auth(env.key))
    env.session.refresh(env.row)
    first = env.row.last_used_at
    assert first is not None
    # Immediate second request must NOT update again (throttled to ≤ once/min).
    client.get(PROJECTS, headers=auth(env.key))
    env.session.refresh(env.row)
    assert env.row.last_used_at == first
