"""One error vocabulary, registered once (#99).

Before this, the app had two overlapping conventions. The documented one was
``LookupError`` → 404, ``ValueError`` → 422. But roughly twenty services raised
``ValueError(f"project '{id}' not found")``, and five routers recovered the
distinction by reading the message:

    if "project" in str(exc) and "not found" in str(exc):
        raise HTTPException(404, "Project not found")
    raise HTTPException(422, str(exc))

The status of a response therefore depended on the *wording* of a service's
message. Rewording one, or adding any new ``ValueError``, silently flipped a 404
to a 422 or the reverse, and nothing failed.

These tests pin the properties that make that class of bug impossible, not the
individual call sites:

1. status follows the exception **type**, never the message text;
2. the handlers are registered app-wide, so a router needs no ``try/except``;
3. the two inverted raises in ``doc_service`` are the right way round;
4. an unexpected exception still produces the shape each surface promises.
"""
import pytest
from app.core.exceptions import ConflictError, NotFoundError
from fastapi import FastAPI
from fastapi.testclient import TestClient

_EMPTY_JSON = '{"type": "doc", "content": [{"type": "paragraph"}]}'


def _seed(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-err"}).json()
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-err"},
    ).json()["id"]


# ---------------------------------------------------------------------------
# 1. Status follows the type, not the message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "detail",
    [
        "project 'p_x' not found",  # the wording the string-match keyed on
        "Project X missing",  # the issue's own counter-example
        "",  # no message at all
        "not found project",  # right words, wrong order
    ],
)
def test_not_found_is_404_whatever_the_message_says(detail: str) -> None:
    """The old code needed the words "project" AND "not found", in that order,
    to produce a 404. Three of these four strings would have become a 422."""
    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise NotFoundError(detail)

    from app.main import create_app  # registered by the real factory

    real = create_app()
    app.exception_handlers = real.exception_handlers
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/boom").status_code == 404


def test_a_validation_error_is_422_even_when_it_mentions_a_missing_project() -> None:
    """The mirror of the above, and the `links.py` bug specifically: that router
    mapped *any* ValueError to 404 'Project not found'. A genuine validation
    failure was reported to the client as a missing row."""
    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise ValueError("project 'p_x' not found — but this is a validation error")

    from app.main import create_app

    app.exception_handlers = create_app().exception_handlers
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/boom").status_code == 422


def test_not_found_error_is_a_lookup_error() -> None:
    """The subclassing is load-bearing: 37 pre-existing `raise LookupError` sites
    and every `except LookupError` keep working, so the vocabularies converged
    without a flag day."""
    assert issubclass(NotFoundError, LookupError)
    assert isinstance(NotFoundError("x"), LookupError)


# ---------------------------------------------------------------------------
# 2. Registered app-wide — the routers carry nothing
# ---------------------------------------------------------------------------


def test_missing_project_is_404_through_a_router_with_no_try_except(
    client: TestClient,
) -> None:
    """`tasks.py` used to string-match to produce this 404. It now has no
    exception handling at all; the app-wide handler does it."""
    res = client.post("/api/v1/projects/p_missing/tasks", json={"title": "T"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.parametrize(
    "path,payload",
    [
        # Bodies must be schema-valid, or the 422 comes from request validation
        # and the test proves nothing about the exception vocabulary.
        ("/api/v1/projects/p_missing/decisions", {"title": "X", "decision": "do it"}),
        ("/api/v1/projects/p_missing/milestones", {"title": "X"}),
        ("/api/v1/projects/p_missing/risks", {"title": "X", "severity": "low"}),
        ("/api/v1/projects/p_missing/phases", {"title": "X"}),
    ],
)
def test_every_router_that_string_matched_still_returns_404(
    client: TestClient, path: str, payload: dict
) -> None:
    """The other four of the five. Same assertion, no shared code path left."""
    res = client.post(path, json=payload)
    assert res.status_code == 404


def test_no_router_matches_on_a_message_any_more() -> None:
    """The guard that keeps this from coming back: no endpoint may branch on the
    text of an exception. This is what the fix actually removed."""
    import pathlib

    offenders = [
        p.name
        for p in pathlib.Path("app/api/v1/endpoints").glob("*.py")
        if "in str(exc)" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"routers matching on exception text: {offenders}"


# ---------------------------------------------------------------------------
# 3. The two inverted raises in doc_service
# ---------------------------------------------------------------------------


def test_a_version_conflict_is_409_not_404(client: TestClient) -> None:
    """Was: service raised LookupError (→404 by convention), and the router
    re-mapped LookupError→409 locally. Two inversions to reach the right answer."""
    pid = _seed(client)
    doc = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "D", "doc_type": "spec"}
    ).json()
    client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": _EMPTY_JSON, "markdown_cache": "a"},
    )
    stale = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": _EMPTY_JSON, "markdown_cache": "b"},
    )
    assert stale.status_code == 409


def test_a_missing_doc_is_404_not_409(client: TestClient) -> None:
    """The other half of the same inversion: the router's `except ValueError →
    404` sat *above* `except LookupError → 409`, so once the service started
    raising NotFoundError (a LookupError) this became a 409."""
    res = client.patch(
        "/api/v1/docs/doc_missing",
        json={"version": 1, "content_json": _EMPTY_JSON, "markdown_cache": "x"},
    )
    assert res.status_code == 404


def test_doc_service_raises_conflict_for_a_conflict() -> None:
    """Pinned at the service boundary too — the HTTP status is downstream of this."""
    assert not issubclass(ConflictError, LookupError)


# ---------------------------------------------------------------------------
# 4. The catch-all: no surface falls back to text/plain
# ---------------------------------------------------------------------------


def _boom_client() -> TestClient:
    """A real app with one route that fails unexpectedly.

    ``base_url`` must be an allowlisted host — the app-wide Host guard answers 403
    for the default ``testserver`` and the request never reaches a handler.
    ``raise_server_exceptions=False`` makes TestClient return the 500 instead of
    re-raising, which is the whole point of what is being tested.
    """
    from app.main import create_app

    app = create_app()

    @app.get("/api/v1/_boom")
    def boom():
        raise RuntimeError("connection string postgresql://user:pw@host/db")

    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def test_an_unexpected_exception_is_json_not_starlette_plain_text() -> None:
    """Without a catch-all, Starlette answers `text/plain` "Internal Server
    Error" — which breaks the problem+json shape /api/external advertises."""
    with _boom_client() as c:
        res = c.get("/api/v1/_boom")
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/json")
    assert res.json() == {"detail": "internal error"}


def test_the_catch_all_never_echoes_the_exception_text() -> None:
    """This is the branch where nobody vetted the message, so the message never
    reaches the client. `str(exc)` here could be a SQL fragment or a DSN."""
    with _boom_client() as c:
        body = c.get("/api/v1/_boom").text
    assert "postgresql" not in body
    assert "pw@host" not in body
