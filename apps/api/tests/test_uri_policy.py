"""One URI policy for stored links and rich content (#118).

Three policies used to disagree: the notes UI normalized to http(s), `LinkCreate`
blocked three literal prefixes and permitted `file:` and custom schemes, and
document JSON was checked for syntax and size but never for what its href/src
attributes pointed at. Import and direct API calls reached none of the frontend
checks at all.
"""
import json

import pytest
from app.core.uri_policy import (
    check_rich_content,
    is_allowed_link,
    normalize_image_src,
    normalize_link,
)
from app.core.utils import new_id, now_utc
from app.models.link import Link
from app.services import uri_audit

# --- the policy itself ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a/b?c=d#e",
        "http://localhost:5173/docs",
        "http://127.0.0.1:8000",
        "mailto:someone@example.com",
        "https://example.com/path_(with_parens)",
    ],
)
def test_ordinary_links_still_work(url):
    assert normalize_link(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "vbscript:msgbox(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "planarus://open/project",
        "about:blank",
        "blob:https://example.com/abc",
    ],
)
def test_disallowed_schemes_are_refused(url):
    with pytest.raises(ValueError):
        normalize_link(url)


#: Built with `chr()` rather than written literally: most of these are invisible,
#: and a literal one in this file would be unreviewable in exactly the way the
#: policy exists to prevent.
ZERO_WIDTH_SPACE = chr(0x200B)
BIDI_OVERRIDE = chr(0x202E)


@pytest.mark.parametrize(
    "url",
    [
        "java\tscript:alert(1)",  # browsers strip the tab before parsing the scheme
        "java\nscript:alert(1)",
        "\x00javascript:alert(1)",
        f"https://exa{ZERO_WIDTH_SPACE}mple.com",
        f"https://example.com/{BIDI_OVERRIDE}evil",
        "https://example.com\\@evil.test",  # backslash: browsers read it as "/"
        "https://exa mple.com",
    ],
)
def test_control_and_invisible_characters_are_refused(url):
    with pytest.raises(ValueError):
        normalize_link(url)


def test_credentials_in_the_authority_are_refused():
    # Reads as trusted.example to a human, resolves to evil.test.
    with pytest.raises(ValueError, match="credentials"):
        normalize_link("https://trusted.example@evil.test/")


@pytest.mark.parametrize("url", ["https://", "https://.example.com", "https://exa..mple.com"])
def test_malformed_hosts_are_refused(url):
    with pytest.raises(ValueError):
        normalize_link(url)


def test_relative_references_are_content_only():
    # A `Link` row is an absolute bookmark; a document reference resolves against
    # the app's own origin and is no more dangerous than in-app navigation.
    with pytest.raises(ValueError):
        normalize_link("/docs/x")
    assert normalize_link("/docs/x", allow_relative=True) == "/docs/x"
    assert normalize_link("#section", allow_relative=True) == "#section"


def test_scheme_relative_is_not_a_relative_reference():
    with pytest.raises(ValueError, match="scheme-relative"):
        normalize_link("//evil.test/x", allow_relative=True)


# --- images -----------------------------------------------------------------


def test_pasted_image_data_uris_are_allowed():
    """The paste path inlines images as base64 data URIs (DocsPanel.imageToDataUrl),
    so refusing `data:` outright would break a feature that ships today."""
    src = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    assert normalize_image_src(src) == src


@pytest.mark.parametrize(
    "src",
    [
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",  # a document, not a raster
        "data:image/svg+xml,<svg onload=alert(1)>",
        "data:text/html;base64,PHNjcmlwdD4=",
        "data:image/png,notbase64",
        "javascript:alert(1)",
    ],
)
def test_unsafe_image_sources_are_refused(src):
    with pytest.raises(ValueError):
        normalize_image_src(src)


def test_remote_images_are_allowed_on_purpose():
    """Documented tradeoff: an http(s) image makes the reader's browser call a
    third party when the document opens. The toolbar's "insert image by URL"
    depends on it, and the CSP img-src is written to match."""
    assert normalize_image_src("https://cdn.example.com/a.png").endswith("a.png")


# --- the rich-content sweep -------------------------------------------------


def _tiptap(href):
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "x", "marks": [{"type": "link", "attrs": {"href": href}}]}
                ],
            }
        ],
    }


def test_rich_content_accepts_a_normal_document():
    check_rich_content(_tiptap("https://example.com"), "content_json")


def test_rich_content_rejects_a_buried_javascript_href():
    with pytest.raises(ValueError):
        check_rich_content(_tiptap("javascript:alert(1)"), "content_json")


def test_rich_content_sweeps_excalidraw_element_links_and_files():
    """The canvas stores scenes in the same column: elements carry `link`, and
    binary files carry `dataURL`."""
    scene = {
        "type": "excalidraw",
        "elements": [{"id": "e1", "type": "rectangle", "link": "javascript:alert(1)"}],
        "files": {},
    }
    with pytest.raises(ValueError):
        check_rich_content(scene, "content_json")

    scene["elements"][0]["link"] = "https://example.com"
    scene["files"] = {"f1": {"mimeType": "image/svg+xml", "dataURL": "data:image/svg+xml,<svg/>"}}
    with pytest.raises(ValueError):
        check_rich_content(scene, "content_json")


def test_rich_content_walk_survives_a_deep_tree():
    """Iterative on purpose: the input is hostile by assumption, and a recursive
    walk would blow the stack on exactly the payload it exists to reject."""
    node: dict = {"attrs": {"href": "https://example.com"}}
    for _ in range(5000):
        node = {"content": [node]}
    check_rich_content(node, "content_json")


def test_a_null_link_is_not_a_violation():
    # Excalidraw writes `link: null` on every element that has no link.
    check_rich_content({"elements": [{"link": None}, {"link": ""}]}, "content_json")


# --- the API surface --------------------------------------------------------


@pytest.fixture(name="project")
def project_fixture(client):
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "wuri"}).json()["id"]
    return client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "puri"}
    ).json()["id"]


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>", "/relative"]
)
def test_direct_api_cannot_store_a_disallowed_link(client, project, url, session):
    r = client.post(
        f"/api/v1/projects/{project}/links",
        json={"entity_type": "project", "entity_id": project, "url": url},
    )
    assert r.status_code == 422, r.text
    assert client.get(f"/api/v1/projects/{project}/links").json() == []


def test_direct_api_still_stores_ordinary_links(client, project):
    for url in ("https://example.com/x", "mailto:a@example.com"):
        r = client.post(
            f"/api/v1/projects/{project}/links",
            json={"entity_type": "project", "entity_id": project, "url": url},
        )
        assert r.status_code == 201, r.text


def test_malformed_document_uris_are_rejected_before_persistence(client, project):
    doc = client.post(
        f"/api/v1/projects/{project}/docs", json={"title": "D", "doc_type": "note"}
    ).json()
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": json.dumps(_tiptap("javascript:alert(1)"))},
    )
    assert r.status_code == 422, r.text
    assert "javascript" not in client.get(f"/api/v1/docs/{doc['id']}").json()["content_json"]


def test_document_image_src_is_swept_too(client, project):
    doc = client.post(
        f"/api/v1/projects/{project}/docs", json={"title": "D2", "doc_type": "note"}
    ).json()
    scene = {"type": "doc", "content": [{"type": "image", "attrs": {"src": "javascript:alert(1)"}}]}
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": json.dumps(scene)},
    )
    assert r.status_code == 422, r.text


# --- import -----------------------------------------------------------------


def _export(client, project):
    return client.get(f"/api/v1/projects/{project}/export").json()


def test_import_cannot_introduce_a_disallowed_link(client, project):
    client.post(
        f"/api/v1/projects/{project}/links",
        json={"entity_type": "project", "entity_id": project, "url": "https://example.com"},
    )
    payload = _export(client, project)
    ws = client.post("/api/v1/workspaces", json={"name": "T", "slug": "turi"}).json()["id"]

    before = len(client.get("/api/v1/projects").json())
    payload["links"][0]["url"] = "javascript:alert(1)"
    r = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": payload})
    assert r.status_code == 422, r.text
    # #117's contract: rejected in full, before the first row is created.
    assert len(client.get("/api/v1/projects").json()) == before


def test_import_cannot_introduce_a_disallowed_document_uri(client, project):
    doc = client.post(
        f"/api/v1/projects/{project}/docs", json={"title": "D3", "doc_type": "note"}
    ).json()
    client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": json.dumps(_tiptap("https://example.com"))},
    )
    payload = _export(client, project)
    ws = client.post("/api/v1/workspaces", json={"name": "T2", "slug": "turi2"}).json()["id"]

    target = next(d for d in payload["docs"] if d["id"] == doc["id"])
    target["content_json"] = json.dumps(_tiptap("javascript:alert(1)"))
    r = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": payload})
    assert r.status_code == 422, r.text


def test_a_clean_export_still_round_trips(client, project):
    client.post(
        f"/api/v1/projects/{project}/links",
        json={"entity_type": "project", "entity_id": project, "url": "https://example.com/ok"},
    )
    payload = _export(client, project)
    ws = client.post("/api/v1/workspaces", json={"name": "T3", "slug": "turi3"}).json()["id"]
    r = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": payload})
    assert r.status_code == 201, r.text


# --- the legacy audit -------------------------------------------------------


def test_audit_finds_rows_written_before_the_policy(client, project, session):
    """`LinkCreate` used to permit `file:` explicitly, so rows like this exist.
    They are reported, never rewritten — see `uri_audit` for why."""
    session.add(
        Link(
            id=new_id("lnk"),
            project_id=project,
            entity_type="project",
            entity_id=project,
            url="file:///etc/passwd",
            title=None,
            created_at=now_utc(),
        )
    )
    session.commit()

    report = uri_audit.audit_stored_uris(session)
    assert [row["url"] for row in report["links"]] == ["file:///etc/passwd"]
    assert report["total"] == 1


def test_audit_is_quiet_on_a_clean_database(client, project, session):
    client.post(
        f"/api/v1/projects/{project}/links",
        json={"entity_type": "project", "entity_id": project, "url": "https://example.com"},
    )
    assert uri_audit.audit_stored_uris(session)["total"] == 0


def test_is_allowed_link_never_raises():
    assert is_allowed_link("https://example.com") is True
    assert is_allowed_link("javascript:alert(1)") is False
    assert is_allowed_link("") is False
