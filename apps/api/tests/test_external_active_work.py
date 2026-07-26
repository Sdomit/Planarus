"""#93: getActiveWork on the external REST/GPT surface.

Before this, a Custom GPT needed four round trips (summary + tasks + decisions +
risks) to learn what one call already returns — and still could not see blockers
or resolve the phase_id on any row, because neither was reachable from this
surface at all.

This widens an authorization-gated surface, so the scope and tier tests below
matter more than the happy path.
"""
import json
from types import SimpleNamespace

import pytest
from app.core.utils import new_id, now_utc
from app.models.blocker import Blocker
from app.models.phase import Phase
from app.models.task import Task
from app.prompt.boundary import PRECEDENCE_SENTENCE

from tests.external_util import auth, issue_key, seed

PATH = "/api/external/v1/projects/{pid}/active-work"


@pytest.fixture
def env(client, external_api, session):
    ws, proj = seed(client, "aw")
    now = now_utc()
    phase = Phase(
        id=new_id("ph"), project_id=proj, title="Discovery", status="active",
        sort_order=0, created_at=now, updated_at=now,
    )
    session.add(phase)
    session.add(
        Task(
            id=new_id("tsk"), project_id=proj, phase_id=phase.id,
            title="Wire the importer", status="in_progress", sort_order=0,
            created_at=now, updated_at=now,
        )
    )
    session.add(
        Blocker(
            id=new_id("blk"), project_id=proj, title="Waiting on vendor key",
            status="open", created_at=now, updated_at=now,
        )
    )
    session.commit()
    _cm, raw = issue_key(client, ws, [proj], can_read=True, can_propose=False)
    return SimpleNamespace(ws=ws, proj=proj, phase=phase.id, key=raw)


def test_active_work_is_reachable_with_a_read_key(env, client):
    res = client.get(PATH.format(pid=env.proj), headers=auth(env.key))
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"metadata", "text"}
    assert PRECEDENCE_SENTENCE in body["text"]


def test_one_call_returns_what_previously_took_four(env, client):
    """Tasks, blockers and the phase roster in a single orientation response."""
    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    assert "Wire the importer" in body["text"]
    assert "Waiting on vendor key" in body["text"]
    assert "Discovery" in body["text"]
    assert body["metadata"]["open_blocker_count"] == 1
    assert body["metadata"]["active_phase_id"] == env.phase


def test_phase_ids_are_resolvable_from_metadata(env, client):
    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    assert body["metadata"]["phase_ids"] == [env.phase]


def test_titles_stay_out_of_metadata(env, client):
    """This surface's core contract: safe scalars only in metadata."""
    body = client.get(PATH.format(pid=env.proj), headers=auth(env.key)).json()
    flat = json.dumps(body["metadata"])
    assert "Wire the importer" not in flat
    assert "Waiting on vendor key" not in flat
    assert "Discovery" not in flat


def test_out_of_scope_project_is_refused(env, client, session):
    """A key scoped to one project must not orient itself in another."""
    _ws2, other = seed(client, "aw2")
    res = client.get(PATH.format(pid=other), headers=auth(env.key))
    assert res.status_code in (403, 404)
    assert "Wire the importer" not in res.text


def test_no_key_is_refused(env, client):
    assert client.get(PATH.format(pid=env.proj)).status_code == 401


def test_bad_key_is_refused(env, client):
    res = client.get(PATH.format(pid=env.proj), headers=auth("agbk_nope_nope"))
    assert res.status_code == 401


def test_route_is_read_only(env, client):
    """No write verb is mounted here — this is an orientation read, nothing else."""
    for verb in (client.post, client.patch, client.delete, client.put):
        res = verb(PATH.format(pid=env.proj), headers=auth(env.key))
        assert res.status_code == 405, f"{verb.__name__} reached the route"
