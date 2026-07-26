"""Phase 7A approval engine: proposal -> review -> approve -> one-time apply -> audit.

The trust core. External callers may only ever create a *pending* proposal (via
``create_proposal``, an internal seam — there is no HTTP proposal-creation route
in Phase 7A). Approve/apply are local-human actions, gated at the route layer by
the local control token. Apply is atomic and idempotent: a compare-and-swap moves
approved -> applying, the target is revalidated inside the same transaction, and
any mismatch invalidates the proposal *without mutating canonical state*.

Audit rule: exactly one AuditEvent per lifecycle transition. The patch *values*
are never written to audit — only field names, checksums, and target identity.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer
from sqlmodel import Session, select

from app.core.exceptions import (
    ApprovalApplyError,
    ApprovalConflictError,
    PolicyError,
    SecretDetectedError,
)
from app.core.utils import new_id, now_utc, now_utc_plus_hours, sha256_hex
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.entity_connection import EntityConnection
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.models.task import Task
from app.policy import allowlist, binding, handlers
from app.prompt import secrets as secret_scan
from app.services import entity_connection_service
from app.services.audit_service import create_audit_event

# Proposals expire 24h after creation. Expiry is a backstop; the patch checksum +
# target fingerprint compare-and-swap is the real freshness guard.
APPROVAL_TTL_HOURS: float = 24.0

_TARGET_MODELS = {
    "task": Task,
    "decision": Decision,
    "doc": Doc,
    "entity_connection": EntityConnection,
}
_TERMINAL = ("applied", "rejected", "expired", "invalidated", "failed")
# A proposal is "active" (still blocks an identical idempotent duplicate) while it
# can still be applied. "failed" is included because apply() treats it as
# retryable — so an identical re-proposal dedupes to the existing failed one
# rather than creating a second row that could double-apply. Only the truly
# terminal states (applied/rejected/expired/invalidated) free the idempotency key.
# MUST mirror the partial unique index in the model AND migration 0006.
_ACTIVE_STATUSES = ("pending", "approved", "applying", "failed")


def _find_active_by_idempotency(
    session: Session, origin: str, actor_ref: str, key: str
) -> Optional[ApprovalRequest]:
    """Return an existing active proposal matching the idempotency triple, if any."""
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.origin == origin,
        ApprovalRequest.actor_ref == actor_ref,
        ApprovalRequest.idempotency_key == key,
        ApprovalRequest.status.in_(_ACTIVE_STATUSES),
    )
    return session.exec(stmt).first()


# --- internal helpers --------------------------------------------------------


def _is_expired(ar: ApprovalRequest) -> bool:
    # ISO-8601 UTC strings with identical offset compare chronologically as text.
    return now_utc() >= ar.expires_at


def _base_payload(ar: ApprovalRequest) -> dict:
    """Audit metadata. NEVER includes patch values or secrets — field names only."""
    try:
        fields = sorted(json.loads(ar.proposed_patch_json).keys())
    except (json.JSONDecodeError, AttributeError):
        fields = []
    return {
        "approval_id": ar.id,
        "action_type": ar.action_type,
        "target_entity_type": ar.target_entity_type,
        "target_entity_id": ar.target_entity_id,
        "patch_checksum": ar.patch_checksum,
        "fields": fields,
        "origin": ar.origin,
        "status": ar.status,
    }


def _audit(
    session: Session,
    ar: ApprovalRequest,
    event_type: str,
    *,
    actor_type: str = "human",
    payload: Optional[dict] = None,
) -> AuditEvent:
    return create_audit_event(
        session,
        event_type=event_type,
        actor_type=actor_type,
        entity_type="approval_request",
        entity_id=ar.id,
        workspace_id=ar.workspace_id,
        project_id=ar.project_id,
        payload_json=json.dumps(payload if payload is not None else _base_payload(ar)),
    )


def _validate_dependencies(
    session: Session,
    action_type: str,
    project_id: str,
    patch: dict,
    target_entity_id: Optional[str],
    base_versions: dict,
    policy: "allowlist.ActionPolicy",
) -> frozenset[str]:
    """Validate every declared reference field against canonical project ownership.

    Returns the set of *patch* keys (a subset of ``policy.reference_fields``) that
    were present, non-null, and validated as an existing, project-owned reference —
    exactly the keys safe to exempt from secret scanning (a reference is exempt
    *because* it was validated, never by prefix or entropy). Raises a GENERIC
    ``PolicyError`` (no value echo) on any missing / cross-project / inconsistent
    reference; the caller writes no row or audit on that failure.

    Read-only: validates existence/ownership and records base versions for stale
    detection; never mutates. Also runs at approve/apply time via ``_revalidate``
    (where the returned set is ignored).
    """
    if action_type == "connection.create":
        try:
            entity_connection_service.validate_connection_values(
                session, project_id, patch
            )
        except LookupError:
            raise PolicyError("referenced connection endpoint is not valid in this project")
        except ValueError as exc:
            raise PolicyError(str(exc))
        return frozenset({"source_entity_id", "target_entity_id"})

    reference_fields = policy.reference_fields
    if not reference_fields:
        return frozenset()

    validated: set[str] = set()
    effective_phase = patch.get("phase_id")
    effective_stage = patch.get("stage_id")
    existing = None
    if action_type == "task.update" and target_entity_id is not None:
        existing = session.get(Task, target_entity_id)
    if "phase_id" not in patch and existing is not None:
        effective_phase = existing.phase_id
    if "stage_id" not in patch and existing is not None:
        effective_stage = existing.stage_id

    if "phase_id" in reference_fields and effective_phase is not None:
        phase = session.get(Phase, effective_phase)
        if phase is None or phase.project_id != project_id:
            raise PolicyError("referenced phase is not a valid phase in this project")
        base_versions[effective_phase] = phase.updated_at
        if patch.get("phase_id") is not None:
            validated.add("phase_id")
    if "stage_id" in reference_fields and effective_stage is not None:
        stage = session.get(Stage, effective_stage)
        if stage is None or stage.project_id != project_id:
            raise PolicyError("referenced stage is not a valid stage in this project")
        if effective_phase is not None and stage.phase_id != effective_phase:
            raise PolicyError("referenced stage does not belong to the referenced phase")
        base_versions[effective_stage] = stage.updated_at
        if patch.get("stage_id") is not None:
            validated.add("stage_id")

    return frozenset(validated)


def _revalidate(
    session: Session, ar: ApprovalRequest, lock_target: bool = False
) -> Optional[str]:
    """Re-check every binding. Returns a reason string if stale, else None.

    Never mutates or commits. ``lock_target`` additionally takes a row lock on
    the target for the rest of the transaction — see the note in ``apply``. Only
    the apply path needs it: the read-only detail view must not hold locks, and
    ``approve`` writes nothing but the approval row.
    """
    if ar.policy_version != allowlist.POLICY_VERSION:
        return "policy version changed"
    try:
        policy = allowlist.get_policy(ar.action_type)
    except PolicyError:
        return "action no longer allowed"

    try:
        patch = json.loads(ar.proposed_patch_json)
    except json.JSONDecodeError:
        return "stored patch is unreadable"
    try:
        normalized = allowlist.normalize_patch(ar.action_type, patch)
        if ar.action_type == "connection.create":
            normalized = entity_connection_service.normalize_connection_patch(normalized)
    except PolicyError:
        return "patch no longer satisfies policy"
    if binding.patch_checksum(normalized) != ar.patch_checksum:
        return "patch checksum mismatch"

    if session.get(Project, ar.project_id) is None:
        return "project no longer exists"

    if not policy.is_create:
        model = _TARGET_MODELS.get(ar.target_entity_type or "")
        if model is None:
            return "unknown target type"
        # Passing with_for_update at all (even False) forces a re-SELECT, so the
        # unlocked callers keep the plain identity-map read they had before.
        target = (
            session.get(model, ar.target_entity_id, with_for_update=True)
            if lock_target
            else session.get(model, ar.target_entity_id)
        )
        if target is None:
            return "target no longer exists"
        if target.project_id != ar.project_id:
            return "target project mismatch"
        if (
            binding.target_fingerprint(policy.allowed_fields, target)
            != ar.base_target_fingerprint
        ):
            return "target changed since proposal"

    try:
        _validate_dependencies(
            session, ar.action_type, ar.project_id, normalized, ar.target_entity_id, {}, policy
        )
    except PolicyError as exc:
        return exc.detail
    return None


# --- public API --------------------------------------------------------------


def create_proposal(
    session: Session,
    *,
    project_id: str,
    action_type: str,
    patch: dict,
    target_entity_id: Optional[str] = None,
    actor_ref: str = "local",
    origin: str = "local",
    derive_idempotency: bool = False,
) -> ApprovalRequest:
    """Create a pending proposal. Internal seam — not exposed over HTTP.

    Raises ``LookupError`` (missing project/target), ``PolicyError`` (bad
    action/field/precondition/oversize), or ``SecretDetectedError`` (secret in a
    value). No ApprovalRequest row is created on any rejection.

    When ``derive_idempotency`` is True (the Phase 7B MCP path), a server-side
    idempotency key is derived from ``origin + actor_ref + workspace + project +
    action + target + patch_checksum``; if an identical *active* proposal already
    exists it is returned instead of creating a duplicate. Phase 7A local callers
    omit this flag and are unaffected (key stays NULL → no dedupe).
    """
    project = session.get(Project, project_id)
    if project is None:
        raise LookupError(f"project '{project_id}' not found")

    policy = allowlist.get_policy(action_type)
    normalized = allowlist.normalize_patch(action_type, patch)
    if action_type == "connection.create":
        normalized = entity_connection_service.normalize_connection_patch(normalized)

    serialized = binding.canonical_json(normalized)
    if len(serialized.encode("utf-8")) > policy.max_patch_bytes:
        raise PolicyError("proposed patch exceeds size limit")

    target_entity_type = policy.target_entity_type
    base_fingerprint: Optional[str] = None
    base_versions: dict = {}

    if policy.is_create:
        if target_entity_id is not None:
            raise PolicyError(f"{action_type} must not target an existing entity")
    else:
        if target_entity_id is None:
            raise PolicyError(f"{action_type} requires a target entity id")
        model = _TARGET_MODELS[target_entity_type]
        target = session.get(model, target_entity_id)
        if target is None:
            raise LookupError(f"{target_entity_type} '{target_entity_id}' not found")
        if target.project_id != project_id:
            raise PolicyError("target belongs to a different project")
        base_fingerprint = binding.target_fingerprint(policy.allowed_fields, target)
        base_versions[target_entity_id] = getattr(target, "updated_at", None)

    # Canonical reference validation BEFORE the secret scan. Returns the patch keys
    # validated as existing, project-owned references — the ONLY values exempt from
    # secret scanning. A reference is exempt because it was validated, never by
    # prefix/entropy; an invalid / cross-project / missing reference raises a generic
    # PolicyError here and no row or audit is written.
    validated_refs = _validate_dependencies(
        session, action_type, project_id, normalized, target_entity_id, base_versions, policy
    )

    # Secret-scan every non-null patch value EXCEPT the validated reference fields.
    # Free text (title/description/decision/context/status/priority/due_at) is always
    # scanned; reject before any row or audit is written, never echoing the value.
    for key, value in normalized.items():
        if value is None or key in validated_refs:
            continue
        if secret_scan.scan(str(value), f"patch:{key}"):
            raise SecretDetectedError()

    checksum = binding.patch_checksum(normalized)

    # Server-derived idempotency (Phase 7B). The key is NEVER client-supplied.
    idempotency_key: Optional[str] = None
    if derive_idempotency:
        idempotency_key = sha256_hex(
            "|".join(
                [
                    origin,
                    actor_ref,
                    project.workspace_id,
                    project_id,
                    action_type,
                    target_entity_id or "",
                    checksum,
                ]
            )
        )
        existing = _find_active_by_idempotency(session, origin, actor_ref, idempotency_key)
        if existing is not None:
            return existing

    now = now_utc()
    ar = ApprovalRequest(
        id=new_id("apr"),
        workspace_id=project.workspace_id,
        project_id=project_id,
        origin=origin,
        actor_ref=actor_ref,
        action_type=action_type,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        proposed_patch_json=serialized,
        patch_checksum=checksum,
        base_target_fingerprint=base_fingerprint,
        base_versions_json=binding.canonical_json(base_versions) if base_versions else None,
        policy_version=allowlist.POLICY_VERSION,
        risk_level="low" if policy.is_create else "medium",
        status="pending",
        idempotency_key=idempotency_key,
        created_at=now,
        expires_at=now_utc_plus_hours(APPROVAL_TTL_HOURS),
    )
    session.add(ar)
    try:
        session.flush()
    except IntegrityError:
        # A concurrent identical proposal won the active-idempotency unique index.
        session.rollback()
        if idempotency_key is not None:
            existing = _find_active_by_idempotency(
                session, origin, actor_ref, idempotency_key
            )
            if existing is not None:
                return existing
        raise
    _audit(session, ar, "proposal_created", actor_type="system")
    session.commit()
    session.refresh(ar)
    return ar


def _approval_filters(stmt, project_id: Optional[str], status: Optional[str]):
    """``status`` accepts one value or a comma-separated set.

    The set form exists because the queue's *actionable* rows are not one status
    but three — pending, approved and applying — and every one of them must stay
    reachable no matter how much decided history accumulates in front of it
    (#154 review). A single-value filter left approved/applying stranded.
    """
    if project_id:
        stmt = stmt.where(ApprovalRequest.project_id == project_id)
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        if len(wanted) == 1:
            stmt = stmt.where(ApprovalRequest.status == wanted[0])
        elif wanted:
            stmt = stmt.where(ApprovalRequest.status.in_(wanted))
    return stmt


def count_approvals(
    session: Session,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """Total matching rows, so a bounded list can report what it left out (#103)."""
    stmt = _approval_filters(
        select(func.count()).select_from(ApprovalRequest), project_id, status
    )
    return int(session.exec(stmt).one())


def list_approvals(
    session: Session,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[ApprovalRequest]:
    """#103: bounded, and without dragging every historical patch body through
    Python. ``proposed_patch_json`` is deferred because no list caller reads it —
    ApprovalSummary has no such field — while it is the largest column on the
    table. The detail/apply paths use ``get_approval`` (a plain ``session.get``)
    and are unaffected; touching the attribute on a deferred row still works, it
    just costs a second query, which is the right trade for a list of 200.
    """
    stmt = _approval_filters(select(ApprovalRequest), project_id, status)
    stmt = stmt.options(defer(ApprovalRequest.proposed_patch_json))
    stmt = stmt.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt).all())


def get_approval(session: Session, approval_id: str) -> Optional[ApprovalRequest]:
    return session.get(ApprovalRequest, approval_id)


def get_proposal_audit(session: Session, approval_id: str) -> list[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "approval_request",
            AuditEvent.entity_id == approval_id,
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return list(session.exec(stmt).all())


def applied_entity(
    session: Session, ar: ApprovalRequest
) -> tuple[Optional[str], Optional[str]]:
    """(entity_type, entity_id) of what an applied proposal actually created or
    changed; (None, None) until it applies.

    For ``*.create`` there is no id at proposal time, so ``target_entity_id`` is
    null and this is the only way an agent can learn what it made. The ids live
    solely in the payload of the audit event ``apply`` links through
    ``applied_audit_event_id`` — this reader lives next to that writer on purpose.
    Non-string values are dropped: the callers put these straight into
    scalar-only external metadata.
    """
    if not ar.applied_audit_event_id:
        return (None, None)
    event = session.get(AuditEvent, ar.applied_audit_event_id)
    if event is None or not event.payload_json:
        return (None, None)
    payload = json.loads(event.payload_json)
    entity_type = payload.get("applied_entity_type")
    entity_id = payload.get("applied_entity_id")
    return (
        entity_type if isinstance(entity_type, str) else None,
        entity_id if isinstance(entity_id, str) else None,
    )


def _scene_counts(raw: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """(element count, total text-element chars) for an Excalidraw scene, or
    (None, None) if unparseable. Used for the compact canvas review preview."""
    if not raw:
        return None, None
    try:
        scene = json.loads(raw)
        els = scene.get("elements", []) if isinstance(scene, dict) else []
        text = sum(len(e.get("text", "")) for e in els if isinstance(e, dict))
        return len(els), text
    except (ValueError, TypeError, AttributeError):
        return None, None


def build_diff(session: Session, ar: ApprovalRequest) -> list[dict]:
    """Before/after for the review UI. Patch is already secret-free."""
    try:
        patch = json.loads(ar.proposed_patch_json)
    except json.JSONDecodeError:
        return []

    # A canvas doc.update carries a multi-MB scene JSON; never surface it raw.
    # The decision's review preview is an element-count + extracted-text delta.
    if ar.target_entity_type == "doc":
        before_raw = None
        if ar.target_entity_id:
            doc = session.get(Doc, ar.target_entity_id)
            before_raw = doc.content_json if doc is not None else None
        b_els, b_txt = _scene_counts(before_raw)
        a_els, a_txt = _scene_counts(patch.get("content_json"))
        return [
            {"field": "elements", "before": b_els, "after": a_els},
            {"field": "text_chars", "before": b_txt, "after": a_txt},
        ]

    before: dict = {}
    if ar.target_entity_id and ar.target_entity_type:
        model = _TARGET_MODELS.get(ar.target_entity_type)
        target = session.get(model, ar.target_entity_id) if model else None
        if target is not None:
            for key in patch:
                before[key] = getattr(target, key, None)
    return [
        {"field": key, "before": before.get(key), "after": patch[key]}
        for key in sorted(patch.keys())
    ]


def staleness(session: Session, ar: ApprovalRequest) -> tuple[bool, Optional[str]]:
    """Compute (is_expired, stale_reason) for the detail view. Read-only."""
    is_expired = ar.status in ("pending", "approved") and _is_expired(ar)
    stale_reason = None
    if ar.status in ("pending", "approved") and not is_expired:
        stale_reason = _revalidate(session, ar)
    return is_expired, stale_reason


def approve(
    session: Session, approval_id: str, decided_by: str = "local"
) -> ApprovalRequest:
    ar = session.get(ApprovalRequest, approval_id)
    if ar is None:
        raise LookupError("approval not found")
    if ar.status != "pending":
        raise ApprovalConflictError(
            f"cannot approve an approval in state '{ar.status}'"
        )
    if _is_expired(ar):
        ar.status = "expired"
        ar.decided_at = now_utc()
        _audit(session, ar, "proposal_expired")
        session.commit()
        raise ApprovalConflictError("approval has expired")
    reason = _revalidate(session, ar)
    if reason is not None:
        ar.status = "invalidated"
        ar.decided_at = now_utc()
        ar.failure_reason = reason
        _audit(session, ar, "proposal_invalidated", payload={**_base_payload(ar), "reason": reason})
        session.commit()
        raise ApprovalConflictError(f"approval is stale: {reason}")
    ar.status = "approved"
    ar.decided_at = now_utc()
    ar.decided_by = decided_by
    _audit(session, ar, "proposal_approved")
    session.commit()
    session.refresh(ar)
    return ar


def reject(
    session: Session,
    approval_id: str,
    reason: Optional[str] = None,
    decided_by: str = "local",
) -> ApprovalRequest:
    ar = session.get(ApprovalRequest, approval_id)
    if ar is None:
        raise LookupError("approval not found")
    if ar.status not in ("pending", "approved"):
        raise ApprovalConflictError(
            f"cannot reject an approval in state '{ar.status}'"
        )
    ar.status = "rejected"
    ar.reason = reason
    ar.decided_at = now_utc()
    ar.decided_by = decided_by
    _audit(session, ar, "proposal_rejected", payload={**_base_payload(ar), "reason": reason})
    session.commit()
    session.refresh(ar)
    return ar


def invalidate(
    session: Session, approval_id: str, decided_by: str = "local"
) -> ApprovalRequest:
    ar = session.get(ApprovalRequest, approval_id)
    if ar is None:
        raise LookupError("approval not found")
    if ar.status not in ("pending", "approved", "failed"):
        raise ApprovalConflictError(
            f"cannot invalidate an approval in state '{ar.status}'"
        )
    ar.status = "invalidated"
    ar.decided_at = now_utc()
    ar.decided_by = decided_by
    _audit(
        session,
        ar,
        "proposal_invalidated",
        payload={**_base_payload(ar), "reason": "manually invalidated"},
    )
    session.commit()
    session.refresh(ar)
    return ar


def apply(
    session: Session, approval_id: str, applied_by: str = "local"
) -> ApprovalRequest:
    """Atomically apply an approved (or retryable failed) proposal exactly once."""
    ar = session.get(ApprovalRequest, approval_id)
    if ar is None:
        raise LookupError("approval not found")

    if ar.status == "applied":
        raise ApprovalConflictError("approval has already been applied")
    if ar.status in ("approved", "failed") and _is_expired(ar):
        ar.status = "expired"
        ar.decided_at = now_utc()
        _audit(session, ar, "proposal_expired")
        session.commit()
        raise ApprovalConflictError("approval has expired")
    if ar.status not in ("approved", "failed"):
        raise ApprovalConflictError(
            f"cannot apply an approval in state '{ar.status}'"
        )

    # One-time apply: compare-and-swap approved|failed -> applying. Only one caller
    # can win this transition; a replay/concurrent apply gets rowcount 0.
    cas = session.execute(
        sa_update(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.status.in_(["approved", "failed"]),
        )
        .values(status="applying")
    )
    if cas.rowcount != 1:
        session.rollback()
        raise ApprovalConflictError(
            "approval is no longer applicable (already in progress or applied)"
        )
    session.refresh(ar)  # ar.status == "applying"

    # Full revalidation inside the same transaction (TOCTOU guard), holding a row
    # lock on the target until this transaction ends.
    #
    # The fingerprint check alone is not enough on PostgreSQL. Under READ
    # COMMITTED an unlocked target can be updated by a human between the check
    # and the write below, and the handler's UPDATE ... WHERE id = ? would then
    # silently overwrite the newer value. SQLite never showed this because the
    # CAS above is the transaction's first write, so it already holds the single
    # writer lock across both steps — correctness that was load-bearing by
    # accident, not by design.
    reason = _revalidate(session, ar, lock_target=True)
    if reason is not None:
        ar.status = "invalidated"
        ar.decided_at = now_utc()
        ar.failure_reason = reason
        _audit(session, ar, "proposal_invalidated", payload={**_base_payload(ar), "reason": reason})
        session.commit()
        raise ApprovalConflictError(f"approval is stale: {reason}")

    # Mutate the canonical target. On any unexpected error, roll back the partial
    # mutation and record a failed (retryable) state in a clean transaction.
    try:
        patch = json.loads(ar.proposed_patch_json)
        entity_type, entity_id = handlers.apply_action(
            session,
            action_type=ar.action_type,
            project_id=ar.project_id,
            target_entity_id=ar.target_entity_id,
            patch=patch,
        )
    except Exception as exc:  # noqa: BLE001 — record + re-raise as 500
        session.rollback()
        ar = session.get(ApprovalRequest, approval_id)
        ar.status = "failed"
        ar.failure_reason = type(exc).__name__
        _audit(
            session,
            ar,
            "proposal_apply_failed",
            payload={**_base_payload(ar), "error": type(exc).__name__},
        )
        session.commit()
        raise ApprovalApplyError("failed to apply approved proposal")

    now = now_utc()
    ar.status = "applied"
    ar.applied_at = now
    event = _audit(
        session,
        ar,
        "proposal_applied",
        payload={
            **_base_payload(ar),
            "applied_entity_type": entity_type,
            "applied_entity_id": entity_id,
        },
    )
    session.flush()  # ensure event.id exists before linking
    ar.applied_audit_event_id = event.id
    session.add(ar)
    session.commit()
    session.refresh(ar)
    return ar


def expire_sweep(session: Session) -> int:
    """Mark stale pending/approved proposals expired. Returns the count swept."""
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.status.in_(["pending", "approved"])
    )
    swept = 0
    for ar in session.exec(stmt).all():
        if _is_expired(ar):
            ar.status = "expired"
            ar.decided_at = now_utc()
            _audit(session, ar, "proposal_expired")
            swept += 1
    if swept:
        session.commit()
    return swept
