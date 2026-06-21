"""Phase 7C1a: validation-gated secret-scan exemption for internal reference fields.

A reference field (phase_id/stage_id) is exempt from secret scanning ONLY after it
is validated as an existing, project-owned canonical reference — never by prefix or
entropy. Free text is always scanned. An invalid/spoofed reference fails canonical
validation before storage; no secret can be smuggled through a reference field.
"""
import uuid

import pytest
from sqlmodel import func, select

from app.core.exceptions import PolicyError, SecretDetectedError
from app.core.utils import new_id, now_utc
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.phase import Phase
from app.models.stage import Stage
from app.policy import allowlist
from app.prompt import secrets as secret_scan
from app.services import approval_service
from tests.external_util import auth, issue_key, seed as ext_seed
from tests.mcp_util import propose_cap, seed as mcp_seed

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
SECRET_ASSIGN = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENGbPxRfiCYEXAMPLEKEY"


# --- helpers -----------------------------------------------------------------


def _seed_project(client) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": f"w-{uuid.uuid4().hex[:8]}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{uuid.uuid4().hex[:8]}"},
    ).json()
    return ws["id"], proj["id"]


def _add_phase(session, project_id, phase_id=None) -> str:
    pid = phase_id or new_id("ph")
    now = now_utc()
    session.add(Phase(id=pid, project_id=project_id, title="ph", status="planned",
                      sort_order=0, created_at=now, updated_at=now))
    session.commit()
    return pid


def _add_stage(session, project_id, phase_id, stage_id=None) -> str:
    sid = stage_id or new_id("stg")
    now = now_utc()
    session.add(Stage(id=sid, phase_id=phase_id, project_id=project_id, title="st",
                      status="planned", sort_order=0, created_at=now, updated_at=now))
    session.commit()
    return sid


def _counts(session) -> tuple[int, int]:
    n_ar = int(session.exec(select(func.count()).select_from(ApprovalRequest)).one())
    n_ev = int(session.exec(select(func.count()).select_from(AuditEvent)).one())
    return n_ar, n_ev


def _high_entropy_id(prefix: str) -> str:
    """Generate an id whose RAW text the scanner would flag (proves exemption matters)."""
    for _ in range(2000):
        cand = new_id(prefix)
        if secret_scan.scan(cand, "patch:ref"):
            return cand
    raise AssertionError("could not generate a high-entropy id")


# --- 1. reference false-positive protection (>= 2000 each) --------------------


def test_2000_valid_phase_ids_zero_false_positives(client, session):
    _, proj = _seed_project(client)
    n = 2000
    phase_ids = [new_id("ph") for _ in range(n)]
    now = now_utc()
    session.add_all([Phase(id=p, project_id=proj, title="ph", status="planned",
                           sort_order=0, created_at=now, updated_at=now) for p in phase_ids])
    session.commit()
    # A meaningful fraction of these raw ids WOULD trip the scanner — proves the
    # exemption is doing real work (not a no-op).
    would_flag = sum(1 for p in phase_ids if secret_scan.scan(p, "patch:phase_id"))
    assert would_flag > 0, "expected some random phase ids to look high-entropy"
    falsely_rejected = 0
    for p in phase_ids:
        try:
            ar = approval_service.create_proposal(
                session, project_id=proj, action_type="task.create",
                patch={"title": "t", "phase_id": p})
            assert ar.status == "pending"
        except SecretDetectedError:
            falsely_rejected += 1
    assert falsely_rejected == 0, f"{falsely_rejected}/{n} valid phase_id proposals falsely rejected"


def test_2000_valid_stage_ids_zero_false_positives(client, session):
    _, proj = _seed_project(client)
    ph = _add_phase(session, proj)
    n = 2000
    stage_ids = [new_id("stg") for _ in range(n)]
    now = now_utc()
    session.add_all([Stage(id=s, phase_id=ph, project_id=proj, title="s", status="planned",
                           sort_order=0, created_at=now, updated_at=now) for s in stage_ids])
    session.commit()
    would_flag = sum(1 for s in stage_ids if secret_scan.scan(s, "patch:stage_id"))
    assert would_flag > 0
    falsely_rejected = 0
    for s in stage_ids:
        try:
            ar = approval_service.create_proposal(
                session, project_id=proj, action_type="task.create",
                patch={"title": "t", "stage_id": s})
            assert ar.status == "pending"
        except SecretDetectedError:
            falsely_rejected += 1
    assert falsely_rejected == 0, f"{falsely_rejected}/{n} valid stage_id proposals falsely rejected"


def test_high_entropy_valid_reference_exempt_because_validated(client, session):
    _, proj = _seed_project(client)
    flagged = _high_entropy_id("ph")
    assert secret_scan.scan(flagged, "patch:phase_id"), "id must be scanner-positive pre-fix"
    _add_phase(session, proj, phase_id=flagged)
    ar = approval_service.create_proposal(
        session, project_id=proj, action_type="task.create",
        patch={"title": "t", "phase_id": flagged})
    assert ar.status == "pending"  # exempt because validated, not by prefix/entropy


# --- 2. three proposal surfaces accept valid references ----------------------


def test_valid_reference_local_7a(client, session):
    _, proj = _seed_project(client)
    ph = _add_phase(session, proj)
    st = _add_stage(session, proj, ph)
    ar = approval_service.create_proposal(
        session, project_id=proj, action_type="task.create",
        patch={"title": "t", "phase_id": ph, "stage_id": st})
    assert ar.origin == "local" and ar.status == "pending"


def test_valid_reference_mcp_7b(client, session):
    from app.mcp.tools import propose as propose_tools

    ws, proj = mcp_seed(client, "refmcp")
    ph = _add_phase(session, proj)
    cap = propose_cap(ws, proj)
    res = propose_tools.create_task_proposal(
        session, cap, propose_tools.CreateTaskProposalArgs(project_id=proj, title="t", phase_id=ph))
    assert res.metadata["status"] == "pending"
    ar = session.get(ApprovalRequest, res.metadata["approval_id"])
    assert ar.origin == "mcp" and ar.status == "pending"


def test_valid_reference_external_7c1(client, session, external_api):
    ws, proj = ext_seed(client, "refext")
    ph = _add_phase(session, proj)
    _, raw = issue_key(client, ws, [proj], can_read=False, can_propose=True)
    res = client.post("/api/external/v1/proposals/task", headers=auth(raw),
                      json={"project_id": proj, "title": "t", "phase_id": ph})
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "pending"
    ar = session.get(ApprovalRequest, body["approval_id"])
    assert ar.origin == "api" and ar.status == "pending"


# --- 3. secret rejection remains strict --------------------------------------


def _assert_rejected_no_storage(session, proj, action_type, patch, exc=SecretDetectedError):
    before = _counts(session)
    with pytest.raises(exc) as info:
        approval_service.create_proposal(session, project_id=proj, action_type=action_type, patch=patch)
    assert _counts(session) == before  # no ApprovalRequest, no AuditEvent
    return info


def test_secret_in_title_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "task.create", {"title": f"token {AWS_KEY}"})


def test_secret_in_description_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "task.create", {"title": "t", "description": SECRET_ASSIGN})


def test_secret_in_decision_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "decision.create",
                                {"title": "t", "decision": f"use {SECRET_ASSIGN}"})


def test_secret_in_context_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "decision.create",
                                {"title": "t", "decision": "ok", "context": SECRET_ASSIGN})


def test_secret_like_phase_id_rejected_no_storage_no_echo(client, session):
    _, proj = _seed_project(client)
    # A real secret stuffed into phase_id (with a valid-looking prefix) is NOT a real
    # owned phase → fails canonical validation → rejected before storage, never echoed.
    for value in (f"ph_{AWS_KEY}", AWS_KEY, f"ph_{uuid.uuid4().hex}"):
        info = _assert_rejected_no_storage(session, proj, "task.create",
                                           {"title": "t", "phase_id": value}, exc=PolicyError)
        assert value not in str(info.value.detail) and AWS_KEY not in str(info.value.detail)
    # And the secret never lands in any stored patch.
    rows = session.exec(select(ApprovalRequest)).all()
    assert all(AWS_KEY not in r.proposed_patch_json for r in rows)


def test_secret_like_stage_id_rejected_no_storage_no_echo(client, session):
    _, proj = _seed_project(client)
    info = _assert_rejected_no_storage(session, proj, "task.create",
                                       {"title": "t", "stage_id": f"stg_{AWS_KEY}"}, exc=PolicyError)
    assert AWS_KEY not in str(info.value.detail)


# --- 4. reference validation failures ----------------------------------------


def test_nonexistent_phase_id_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "phase_id": new_id("ph")}, exc=PolicyError)


def test_nonexistent_stage_id_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "stage_id": new_id("stg")}, exc=PolicyError)


def test_cross_project_phase_id_rejected(client, session):
    _, proj_a = _seed_project(client)
    _, proj_b = _seed_project(client)
    ph_a = _add_phase(session, proj_a)
    _assert_rejected_no_storage(session, proj_b, "task.create",
                                {"title": "t", "phase_id": ph_a}, exc=PolicyError)


def test_cross_project_stage_id_rejected(client, session):
    _, proj_a = _seed_project(client)
    _, proj_b = _seed_project(client)
    ph_a = _add_phase(session, proj_a)
    st_a = _add_stage(session, proj_a, ph_a)
    _assert_rejected_no_storage(session, proj_b, "task.create",
                                {"title": "t", "stage_id": st_a}, exc=PolicyError)


def test_stage_under_different_phase_rejected(client, session):
    _, proj = _seed_project(client)
    ph1 = _add_phase(session, proj)
    ph2 = _add_phase(session, proj)
    st1 = _add_stage(session, proj, ph1)
    # stage belongs to ph1 but the proposal claims ph2.
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "phase_id": ph2, "stage_id": st1}, exc=PolicyError)


def test_malformed_reference_id_rejected(client, session):
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "phase_id": "!!! not an id !!!"}, exc=PolicyError)


def test_null_optional_reference_allowed(client, session):
    _, proj = _seed_project(client)
    ar = approval_service.create_proposal(
        session, project_id=proj, action_type="task.create",
        patch={"title": "t", "phase_id": None})
    assert ar.status == "pending"


# --- 5. security regression / invariants -------------------------------------


def test_high_entropy_in_non_reference_field_still_rejected(client, session):
    _, proj = _seed_project(client)
    high_entropy = "Zk7Qp2Wx9Lm4Rt6Yv8Bn1Cs3Df5Gh0Jk2Mp4Qr6Tw8"  # 40+ chars, > threshold
    assert secret_scan.scan(high_entropy, "x"), "control: must be scanner-positive"
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "description": high_entropy})


def test_valid_reference_but_secret_in_free_text_still_rejected(client, session):
    _, proj = _seed_project(client)
    ph = _add_phase(session, proj)
    # A validated reference does NOT exempt other fields: the description is scanned.
    _assert_rejected_no_storage(session, proj, "task.create",
                                {"title": "t", "phase_id": ph, "description": SECRET_ASSIGN})


def test_reference_fields_subset_of_allowed_fields():
    for name in allowlist.APPROVAL_ACTION_TYPES:
        policy = allowlist.get_policy(name)
        assert policy.reference_fields <= policy.allowed_fields, name


def test_validate_dependencies_returns_only_validated_present_references(client, session):
    _, proj = _seed_project(client)
    ph = _add_phase(session, proj)
    st = _add_stage(session, proj, ph)
    tpolicy = allowlist.get_policy("task.create")
    validated = approval_service._validate_dependencies(
        session, "task.create", proj, {"title": "t", "phase_id": ph, "stage_id": st}, None, {}, tpolicy)
    assert validated == frozenset({"phase_id", "stage_id"})
    assert validated <= tpolicy.reference_fields
    # Only the present reference is returned.
    only_phase = approval_service._validate_dependencies(
        session, "task.create", proj, {"title": "t", "phase_id": ph}, None, {}, tpolicy)
    assert only_phase == frozenset({"phase_id"})
    # decision.create declares no reference fields → empty.
    dpolicy = allowlist.get_policy("decision.create")
    assert approval_service._validate_dependencies(
        session, "decision.create", proj, {"title": "t", "decision": "d"}, None, {}, dpolicy) == frozenset()


def test_decision_high_entropy_title_still_scanned(client, session):
    # decision.create has no reference fields; all of its fields stay scanned.
    _, proj = _seed_project(client)
    _assert_rejected_no_storage(session, proj, "decision.create",
                                {"title": f"k {AWS_KEY}", "decision": "ok"})
