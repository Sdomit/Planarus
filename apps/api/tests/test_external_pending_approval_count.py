"""#108: the pending-approval count the browser-extension badge polls.

A bare number only — never approval titles, diffs, or ids — so a read-only key
issued for a browser badge has the smallest blast radius a credential on this
surface can have.
"""
from types import SimpleNamespace

import pytest
from app.services import approval_service

from tests.external_util import auth, issue_key, seed

PATH = "/api/external/v1/projects/{pid}/approvals/pending-count"


@pytest.fixture
def env(client, external_api, session):
    ws, proj = seed(client, "pac")
    _cm, raw = issue_key(client, ws, [proj], can_read=True, can_propose=False)
    return SimpleNamespace(ws=ws, proj=proj, key=raw)


def _propose(session, proj, title):
    return approval_service.create_proposal(
        session, project_id=proj, action_type="task.create", patch={"title": title}
    )


def test_zero_when_nothing_pending(env, client):
    res = client.get(PATH.format(pid=env.proj), headers=auth(env.key))
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"metadata", "text"}
    assert body["metadata"]["pending_count"] == 0


def test_counts_only_pending_rows(env, client, session):
    _propose(session, env.proj, "one")
    _propose(session, env.proj, "two")
    decided = _propose(session, env.proj, "three")
    approval_service.reject(session, decided.id, reason=None, decided_by="local")

    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    assert body["metadata"]["pending_count"] == 2


def test_titles_never_appear_in_the_response(env, client, session):
    _propose(session, env.proj, "SENTINEL_TITLE_DO_NOT_LEAK")
    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    assert "SENTINEL_TITLE_DO_NOT_LEAK" not in body["text"]
    assert "SENTINEL_TITLE_DO_NOT_LEAK" not in str(body["metadata"])


def test_scoped_to_the_requested_project_only(env, client, session):
    _ws2, other = seed(client, "pac2")
    _propose(session, other, "elsewhere")
    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    assert body["metadata"]["pending_count"] == 0


def test_out_of_scope_project_is_refused(env, client):
    _ws2, other = seed(client, "pac3")
    res = client.get(PATH.format(pid=other), headers=auth(env.key))
    assert res.status_code in (403, 404)


def test_no_key_is_refused(env, client):
    assert client.get(PATH.format(pid=env.proj)).status_code == 401


def test_bad_key_is_refused(env, client):
    res = client.get(PATH.format(pid=env.proj), headers=auth("agbk_nope_nope"))
    assert res.status_code == 401


def test_propose_only_key_is_forbidden(env, client):
    """D77: this route is read-only; a propose-scoped key must not reach it."""
    _cm, raw = issue_key(client, env.ws, [env.proj], can_read=False, can_propose=True)
    res = client.get(PATH.format(pid=env.proj), headers=auth(raw))
    assert res.status_code == 403


def test_route_is_read_only(env, client):
    for verb in (client.post, client.patch, client.delete, client.put):
        res = verb(PATH.format(pid=env.proj), headers=auth(env.key))
        assert res.status_code == 405, f"{verb.__name__} reached the route"
