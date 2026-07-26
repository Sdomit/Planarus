"""#98 — a hand-edited governance file must not gut the pack forever.

`context_pack_service` excludes a checksum-drifted governance file, and before
this change nothing could ever put the checksum back: regeneration skipped pinned
rows without re-adopting, the only other checksum writer was the branch that
overwrites the file with scaffold, and the API offered pin/unpin/diff but no
"accept what is on disk". One editor session on `context/AGENT_RULES.md` was
enough to strip the allowed paths, forbidden paths and agent rules out of every
subsequent pack — from a section headed "checksum-verified, authoritative".

Each test here fails against the pre-fix code, either on the assertion named in
its comment or with a 200 where a 409 is now expected.
"""
import os

from app.fsmemory import atomic_io
from app.models.audit_event import AuditEvent
from app.models.context_file import ContextFile
from fastapi.testclient import TestClient
from sqlmodel import Session, select

# All three governance files ship authored=False, so they are generated and
# UNPINNED by default — the common case for a hand edit. NEXT_STEP is authored,
# so it covers the pinned branch of the same trap.
GOVERNANCE = "context/AGENT_RULES.md"
PINNED_FILE = "context/NEXT_STEP.md"
EDITED = "# Agent rules\n\nHand-edited: never touch billing logic.\n"


def _project_with_folder(client: TestClient, tmp_path, slug: str = "gov") -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{slug}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "Gov", "slug": slug, "summary": "s"},
    ).json()
    folder = str(tmp_path / slug)
    os.makedirs(folder)
    # Setting folder_path provisions context/* and creates the ContextFile rows.
    client.patch(f"/api/v1/projects/{proj['id']}", json={"folder_path": folder})
    return proj["id"], folder


def _row(session: Session, pid: str, rel: str = GOVERNANCE) -> ContextFile:
    """Re-read a row. Copy scalars off it before the API commits again.

    The test session's identity map returns the same object every time, so
    holding the row and comparing `before.checksum` to `after.checksum` compares
    a value with itself and passes either way.
    """
    session.expire_all()  # the API committed on another session
    return session.exec(
        select(ContextFile).where(
            ContextFile.project_id == pid, ContextFile.relative_path == rel
        )
    ).one()


def _preview(client: TestClient, pid: str, **overrides):
    body = {
        "profile": "build",
        "target_tool": "claude-sonnet-4-6",
        "budget_preset": "medium",
        "objective": "Implement the login flow",
        "selection": {},
    }
    body.update(overrides)
    return client.post(f"/api/v1/projects/{pid}/context-pack/preview", json=body)


def _file_of(client: TestClient, pid: str, rel: str = GOVERNANCE) -> dict:
    files = client.get(f"/api/v1/context-files?project_id={pid}").json()
    return next(f for f in files if f["relative_path"] == rel)


# ---------------------------------------------------------------------------
# The trap itself
# ---------------------------------------------------------------------------


def test_regeneration_readopts_a_pinned_drifted_file(
    client: TestClient, session: Session, tmp_path
) -> None:
    pid, folder = _project_with_folder(client, tmp_path)
    atomic_io.write_text(folder, PINNED_FILE, EDITED)
    before_sum = _row(session, pid, PINNED_FILE).checksum
    assert _row(session, pid, PINNED_FILE).pinned is True  # authored=True pins

    res = client.post(f"/api/v1/projects/{pid}/context/regenerate")
    assert res.status_code == 200
    outcome = next(o for o in res.json()["outcomes"] if o["relative_path"] == PINNED_FILE)

    # Pre-fix: status pinned, drifted true, and the checksum left stale forever.
    assert outcome["status"] == "pinned-skip"
    assert outcome["drifted"] is True, "the edit is still reported to the human"
    after = _row(session, pid, PINNED_FILE)
    assert after.checksum != before_sum, "checksum re-adopted, not left stale"
    assert after.last_manual_edit_at is not None
    # And the file itself is untouched — pinned still means "never overwrite".
    assert atomic_io.read_text(folder, PINNED_FILE) == EDITED


def test_a_second_regeneration_reports_no_drift(
    client: TestClient, tmp_path
) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov2")
    atomic_io.write_text(folder, PINNED_FILE, EDITED)
    client.post(f"/api/v1/projects/{pid}/context/regenerate")
    res = client.post(f"/api/v1/projects/{pid}/context/regenerate").json()
    outcome = next(o for o in res["outcomes"] if o["relative_path"] == PINNED_FILE)
    assert outcome["drifted"] is False, "drift is resolved, not reported forever"


def test_regeneration_leaves_an_unpinned_edit_for_the_human_to_resolve(
    client: TestClient, session: Session, tmp_path
) -> None:
    """The governance files are generated, so regeneration must NOT auto-adopt.

    Adopting a hand edit to a generated file would silently bless it as the new
    truth; overwriting it would destroy it. Regeneration does neither — it reports
    drift and waits, which is why the explicit adopt action has to exist.
    """
    pid, folder = _project_with_folder(client, tmp_path, "gov9")
    before_sum = _row(session, pid).checksum
    assert _row(session, pid).pinned is False, "AGENT_RULES ships generated, not pinned"
    atomic_io.write_text(folder, GOVERNANCE, EDITED)

    res = client.post(f"/api/v1/projects/{pid}/context/regenerate").json()
    outcome = next(o for o in res["outcomes"] if o["relative_path"] == GOVERNANCE)
    assert outcome["status"] == "drift-skip"
    after = _row(session, pid)
    assert after.checksum == before_sum, "not adopted behind the human's back"
    assert atomic_io.read_text(folder, GOVERNANCE) == EDITED, "and not overwritten"


# ---------------------------------------------------------------------------
# The explicit action
# ---------------------------------------------------------------------------


def test_adopt_clears_drift_and_keeps_the_pin(
    client: TestClient, session: Session, tmp_path
) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov3")
    atomic_io.write_text(folder, GOVERNANCE, EDITED)
    cf = _file_of(client, pid)
    assert client.get(f"/api/v1/context-files/{cf['id']}/content").json()["drifted"] is True

    res = client.post(f"/api/v1/context-files/{cf['id']}/adopt")
    assert res.status_code == 200
    body = res.json()
    assert body["pinned"] is True, "adoption pins, or the next regen overwrites it"
    assert body["checksum"] != cf["checksum"]
    assert body["last_manual_edit_at"] is not None

    content = client.get(f"/api/v1/context-files/{cf['id']}/content").json()
    assert content["drifted"] is False
    assert content["content"] == EDITED  # the edit survived; nothing was overwritten

    session.expire_all()
    events = session.exec(
        select(AuditEvent).where(AuditEvent.entity_id == cf["id"])
    ).all()
    assert any("adopted_checksum" in (e.payload_json or "") for e in events)


def test_regeneration_after_adoption_keeps_the_adopted_content(
    client: TestClient, tmp_path
) -> None:
    """The whole point of pinning on adopt.

    Without it the row is unpinned with a checksum that now matches disk, so
    regeneration takes its final branch and writes the scaffold over the top —
    destroying the edit one call after the human accepted it.
    """
    pid, folder = _project_with_folder(client, tmp_path, "gov10")
    atomic_io.write_text(folder, GOVERNANCE, EDITED)
    cf = _file_of(client, pid)
    client.post(f"/api/v1/context-files/{cf['id']}/adopt")

    client.post(f"/api/v1/projects/{pid}/context/regenerate")
    assert atomic_io.read_text(folder, GOVERNANCE) == EDITED


def test_adopt_is_idempotent(client: TestClient, tmp_path) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov4")
    atomic_io.write_text(folder, GOVERNANCE, EDITED)
    cf = _file_of(client, pid)
    first = client.post(f"/api/v1/context-files/{cf['id']}/adopt").json()
    second = client.post(f"/api/v1/context-files/{cf['id']}/adopt").json()
    assert first["checksum"] == second["checksum"]


def test_adopt_unknown_id_is_404(client: TestClient) -> None:
    assert client.post("/api/v1/context-files/ctx_missing/adopt").status_code == 404


def test_adopt_refuses_when_the_file_is_gone(client: TestClient, tmp_path) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov5")
    cf = _file_of(client, pid)
    os.remove(os.path.join(folder, "context", "AGENT_RULES.md"))
    res = client.post(f"/api/v1/context-files/{cf['id']}/adopt")
    # Adopting nothing would record the checksum of an empty read as if it were
    # content the human wrote.
    assert res.status_code == 409
    assert "not on disk" in res.json()["detail"]


# ---------------------------------------------------------------------------
# The pack refuses instead of footnoting
# ---------------------------------------------------------------------------


def test_preview_refuses_while_a_governance_file_is_excluded(
    client: TestClient, tmp_path
) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov6")
    assert _preview(client, pid).status_code == 200

    atomic_io.write_text(folder, "context/FILES_FORBIDDEN.md", "tampered\n")
    res = _preview(client, pid)
    # Pre-fix this was a 200 carrying one line in `warnings`.
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "FILES_FORBIDDEN" in detail and "drifted" in detail
    assert "adopt" in detail, "the refusal names the way out"


def test_preview_confirm_path_still_warns(client: TestClient, tmp_path) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov7")
    atomic_io.write_text(folder, "context/FILES_FORBIDDEN.md", "tampered\n")
    res = _preview(client, pid, allow_incomplete_governance=True)
    assert res.status_code == 200
    data = res.json()
    assert any("FILES_FORBIDDEN" in w and "incomplete" in w for w in data["warnings"])
    assert "_Unavailable (drifted) — not included._" in data["markdown"]


def test_adopting_makes_the_pack_whole_again(client: TestClient, tmp_path) -> None:
    pid, folder = _project_with_folder(client, tmp_path, "gov8")
    atomic_io.write_text(folder, GOVERNANCE, EDITED)
    assert _preview(client, pid).status_code == 409

    cf = _file_of(client, pid)
    assert client.post(f"/api/v1/context-files/{cf['id']}/adopt").status_code == 200

    res = _preview(client, pid)
    assert res.status_code == 200
    data = res.json()
    # The hand-written rule is now embedded in the authoritative scope section.
    assert "never touch billing logic" in data["markdown"]
    assert not any("AGENT_RULES" in w for w in data["warnings"])
