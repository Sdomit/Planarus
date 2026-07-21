"""Phase 7C1: external API security boundary (host/CORS/cookie/body/problem+json)."""
from types import SimpleNamespace

import pytest

from app.api.external.middleware import _read_capped_body
from tests.external_util import auth, issue_key, seed

PROJECTS = "/api/external/v1/projects"
PROPOSE = "/api/external/v1/proposals/task"


@pytest.fixture
def keys(client, external_api):
    ws, proj = seed(client, "bnd")
    _, raw = issue_key(client, ws, [proj], can_read=True, can_propose=True)
    return SimpleNamespace(ws=ws, proj=proj, key=raw)


# --- disabled by default -----------------------------------------------------


def test_external_disabled_by_default_returns_404(client):
    # No `external_api` fixture → PLANARUS_EXTERNAL_API_ENABLED defaults to False.
    res = client.get(PROJECTS, headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_a_b"})
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
    assert "x-request-id" in {k.lower() for k in res.headers}


# --- host header guard -------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.0.0.1:8000", "[::1]", "[::1]:9000"])
def test_loopback_hosts_accepted(keys, client, host):
    res = client.get(PROJECTS, headers={"Authorization": f"Bearer {keys.key}", "Host": host})
    assert res.status_code == 200  # passes host guard + auth


@pytest.mark.parametrize("host", ["evil.example", "testserver", "169.254.0.1", ""])
def test_foreign_or_missing_host_rejected(keys, client, host):
    res = client.get(PROJECTS, headers={"Authorization": f"Bearer {keys.key}", "Host": host})
    assert res.status_code == 403
    assert res.json()["type"].endswith("/forbidden_host")


def test_x_forwarded_host_is_not_trusted(keys, client):
    res = client.get(
        PROJECTS,
        headers={
            "Authorization": f"Bearer {keys.key}",
            "Host": "evil.example",
            "X-Forwarded-Host": "127.0.0.1",
            "X-Forwarded-For": "127.0.0.1",
            "X-Forwarded-Proto": "http",
        },
    )
    assert res.status_code == 403


def test_configured_allowed_host(keys, client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "external_api_allowed_hosts", "api.internal.example")
    res = client.get(PROJECTS, headers={"Authorization": f"Bearer {keys.key}", "Host": "api.internal.example"})
    assert res.status_code == 200


# --- cookies + CORS ----------------------------------------------------------


def test_cookie_header_rejected(keys, client):
    res = client.get(PROJECTS, headers={**auth(keys.key), "Cookie": "session=abc"})
    assert res.status_code == 403
    assert res.json()["type"].endswith("/cookie_not_allowed")


def test_no_cors_headers_on_external_responses(keys, client):
    res = client.get(PROJECTS, headers={**auth(keys.key), "Origin": "http://localhost:5173"})
    lower = {k.lower() for k in res.headers}
    assert "access-control-allow-origin" not in lower
    assert "access-control-allow-credentials" not in lower


def test_options_preflight_gains_no_cors(keys, client):
    res = client.options(
        PROJECTS,
        headers={
            "Host": "127.0.0.1",
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}
    assert res.status_code in (404, 405)  # no OPTIONS handler; never a CORS 200


def test_internal_routes_still_get_cors():
    # Sanity: the local UI surface keeps its CORS (proves bypass is path-scoped).
    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app, base_url="http://localhost")
    res = c.get("/api/v1/local-session", headers={"Origin": "http://localhost:5173"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


# --- body limits + media type + JSON -----------------------------------------


def test_content_length_over_limit_rejected(keys, client):
    big = "x" * (64 * 1024 + 10)
    res = client.post(PROPOSE, headers=auth(keys.key), json={"project_id": keys.proj, "title": big})
    assert res.status_code == 413
    assert res.json()["type"].endswith("/payload_too_large")


def test_streamed_receive_cap_enforced():
    import anyio

    async def _run():
        chunks = [b"a" * 40000, b"b" * 40000]  # 80k > 64k

        async def fake_receive():
            if chunks:
                return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}
            return {"type": "http.request", "body": b"", "more_body": False}

        body, exceeded = await _read_capped_body(fake_receive, 64 * 1024)
        assert exceeded is True and body == b""

        small = [b"hello"]

        async def fake_receive2():
            if small:
                return {"type": "http.request", "body": small.pop(0), "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        body2, exceeded2 = await _read_capped_body(fake_receive2, 64 * 1024)
        assert exceeded2 is False and body2 == b"hello"

    anyio.run(_run)


def test_wrong_media_type_415(keys, client):
    res = client.post(
        PROPOSE,
        headers={**auth(keys.key), "Content-Type": "text/plain"},
        content="project_id=x",
    )
    assert res.status_code == 415
    assert res.json()["type"].endswith("/unsupported_media_type")


def test_malformed_json_400(keys, client):
    res = client.post(
        PROPOSE,
        headers={**auth(keys.key), "Content-Type": "application/json"},
        content="{not valid json",
    )
    assert res.status_code == 400
    assert res.json()["type"].endswith("/malformed_json")


def test_unknown_field_422(keys, client):
    res = client.post(
        PROPOSE,
        headers=auth(keys.key),
        json={"project_id": keys.proj, "title": "t", "bogus_field": 1},
    )
    assert res.status_code == 422
    assert res.json()["type"].endswith("/validation_error")


# --- request id + leak hygiene ----------------------------------------------


def test_request_id_returned_and_safe(keys, client):
    res = client.get(PROJECTS, headers=auth(keys.key))
    rid = res.headers.get("X-Request-Id")
    assert rid and rid.startswith("req_")
    # 404 problem instance == the request id, and is not a filesystem path.
    res404 = client.get("/api/external/v1/projects/nope/summary", headers=auth(keys.key))
    body = res404.json()
    assert body["instance"] == res404.headers["X-Request-Id"]
    assert "/" not in body["instance"] and "\\" not in body["instance"]


def test_error_bodies_leak_nothing(keys, client):
    res = client.get(PROJECTS, headers={"Host": "127.0.0.1", "Authorization": "Bearer agbk_bad_key"})
    text = res.text.lower()
    for needle in ["traceback", "sqlite", "select ", "c:\\", "/users/", ".py", "secret_hash", "argon2"]:
        assert needle not in text
