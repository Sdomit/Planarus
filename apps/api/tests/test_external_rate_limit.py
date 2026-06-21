"""Phase 7C1: in-process rate limiting (deterministic clock, no sleeping)."""
from types import SimpleNamespace

import pytest

from app.core.rate_limit import RateLimiter
from tests.external_util import auth, issue_key, seed

PROJECTS = "/api/external/v1/projects"


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


# --- unit: bucket logic ------------------------------------------------------


def test_read_bucket_60_per_minute():
    clk = FakeClock()
    rl = RateLimiter(clock=clk)
    for _ in range(60):
        assert rl.check_read("k") is None
    retry = rl.check_read("k")  # 61st
    assert retry is not None and retry > 0
    # New window after 60s.
    clk.advance(60)
    assert rl.check_read("k") is None


def test_propose_bucket_10_per_minute():
    rl = RateLimiter(clock=FakeClock())
    for _ in range(10):
        assert rl.check_propose("k") is None
    assert rl.check_propose("k") is not None


def test_buckets_are_per_key():
    rl = RateLimiter(read_per_min=1, clock=FakeClock())
    assert rl.check_read("a") is None
    assert rl.check_read("b") is None  # different key, own window
    assert rl.check_read("a") is not None


def test_global_auth_failure_bucket():
    rl = RateLimiter(auth_fail_per_min=3, clock=FakeClock())
    assert rl.note_auth_failure() is None
    assert rl.note_auth_failure() is None
    assert rl.note_auth_failure() is None
    assert rl.note_auth_failure() is not None  # 4th throttled


def test_bounded_map_eviction():
    rl = RateLimiter(max_keys=3, clock=FakeClock())
    for i in range(10):
        rl.check_read(f"key{i}")
    assert len(rl._read) <= 3


def test_concurrency_cap_and_release():
    rl = RateLimiter(max_concurrency=2, clock=FakeClock())
    assert rl.acquire("k") is True
    assert rl.acquire("k") is True
    assert rl.acquire("k") is False  # cap reached
    rl.release("k")
    assert rl.acquire("k") is True


# --- route integration -------------------------------------------------------


@pytest.fixture
def keys(client, external_api):
    ws, proj = seed(client, "rl")
    _, raw = issue_key(client, ws, [proj], can_read=True, can_propose=True)
    return SimpleNamespace(ws=ws, proj=proj, key=raw)


def test_route_read_limit_returns_429_with_retry_after(keys, client, monkeypatch):
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "read_per_min", 1)
    assert client.get(PROJECTS, headers=auth(keys.key)).status_code == 200
    res = client.get(PROJECTS, headers=auth(keys.key))
    assert res.status_code == 429
    assert res.headers.get("Retry-After") is not None
    assert res.json()["type"].endswith("/rate_limited")


def test_route_propose_limit_returns_429(keys, client, monkeypatch):
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "propose_per_min", 1)
    body = {"project_id": keys.proj, "title": "t1"}
    assert client.post("/api/external/v1/proposals/task", headers=auth(keys.key), json=body).status_code == 202
    res = client.post("/api/external/v1/proposals/task", headers=auth(keys.key), json={"project_id": keys.proj, "title": "t2"})
    assert res.status_code == 429


def test_limiter_exception_fails_closed_503(keys, client, monkeypatch):
    from app.core.rate_limit import limiter

    def _boom(*a, **k):
        raise RuntimeError("limiter down")

    monkeypatch.setattr(limiter, "check_read", _boom)
    res = client.get(PROJECTS, headers=auth(keys.key))
    assert res.status_code == 503
    assert res.json()["type"].endswith("/limiter_unavailable")


def test_concurrency_exhausted_returns_429(keys, client, monkeypatch):
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "acquire", lambda key_id: False)
    res = client.get(PROJECTS, headers=auth(keys.key))
    assert res.status_code == 429


def test_global_auth_failure_route_throttle(client, external_api, monkeypatch):
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "auth_fail_per_min", 2)
    # Random unknown keys still hit the bounded global failed-auth bucket.
    assert client.get(PROJECTS, headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_a_1"}).status_code == 401
    assert client.get(PROJECTS, headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_b_2"}).status_code == 401
    res = client.get(PROJECTS, headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_c_3"})
    assert res.status_code == 429
