"""Outbound webhooks (Phase 17.3, D38).

Signed, best-effort, outbound-only delivery — a webhook never approves or applies.
Design constraints (all honoured here):

* **No daemon/scheduler.** Deliveries fire at event emission, offloaded to a small
  bounded thread pool so the triggering request never blocks. There is no poller.
* **From existing emit points, no new event bus.** A before/after-commit listener
  on the session turns each committed ``AuditEvent`` (for project-content entities)
  into a webhook of kind ``{entity_type}.{event_type}`` (e.g. ``task.create``).
* **Inert without the key.** Everything short-circuits unless
  ``webhook_crypto.is_enabled()`` (``AGENTBOARD_WEBHOOK_ENC_KEY`` set), so the
  default install and every existing test are unaffected.
* **HMAC-SHA256 signed** with the per-subscription secret (Fernet-encrypted at
  rest). Auto-disabled after too many consecutive failures.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy import event
from sqlmodel import Session, select

from app.core import actor, webhook_crypto
from app.core.utils import new_id, now_utc
from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription

# Project-content entities whose audit events are webhook-eligible. Auth, settings,
# email, api-client, admin, agent-run, workspace, calendar-connection events never
# fire a webhook (no accidental disclosure of management/security activity).
WEBHOOK_ENTITY_TYPES = frozenset(
    {
        "task", "decision", "risk", "blocker", "milestone", "comment", "doc",
        "phase", "stage", "link", "checklist_item", "project",
    }
)

_FAILURE_THRESHOLD = 5
_TIMEOUT_SECONDS = 5

# ponytail: bounded pool, fire-and-forget — matches the app's no-scheduler stance.
# Upgrade to a durable outbox + async worker only if an always-on/hosted consumer
# needs at-least-once delivery.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")


def _submit(fn, *args) -> None:
    """Offload a delivery. Tests monkeypatch this to run inline for determinism."""
    _executor.submit(fn, *args)


# --- subscription management -------------------------------------------------


def create_subscription(
    session: Session,
    *,
    workspace_id: str,
    target_url: str,
    event_kinds: Optional[Iterable[str]] = None,
    project_ids: Optional[Iterable[str]] = None,
    fmt: str = "json",
) -> tuple[WebhookSubscription, str]:
    """Create a subscription and return (row, raw_secret). The raw secret is shown
    exactly once; only its Fernet ciphertext is stored."""
    if urlparse(target_url).scheme not in ("http", "https"):
        raise ValueError("target_url must be an http(s) URL")
    if fmt != "json":  # 17.3a delivers JSON only; slack/discord land in 17.3b.
        raise ValueError("unsupported format")
    raw_secret = secrets.token_urlsafe(32)
    sub = WebhookSubscription(
        id=new_id("whs"),
        workspace_id=workspace_id,
        target_url=target_url,
        secret_enc=webhook_crypto.encrypt(raw_secret),
        event_kinds_json=json.dumps(list(event_kinds or [])),
        project_ids_json=json.dumps(list(project_ids or [])),
        format=fmt,
        enabled=True,
        failure_count=0,
        created_at=now_utc(),
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub, raw_secret


def list_subscriptions(session: Session, workspace_id: Optional[str]) -> list[WebhookSubscription]:
    stmt = select(WebhookSubscription)
    if workspace_id:
        stmt = stmt.where(WebhookSubscription.workspace_id == workspace_id)
    return list(session.exec(stmt))


def to_read(sub: WebhookSubscription) -> dict:
    """Client-safe view — never includes the (encrypted) secret."""
    return {
        "id": sub.id,
        "workspace_id": sub.workspace_id,
        "target_url": sub.target_url,
        "event_kinds": json.loads(sub.event_kinds_json or "[]"),
        "project_ids": json.loads(sub.project_ids_json or "[]"),
        "format": sub.format,
        "enabled": sub.enabled,
        "failure_count": sub.failure_count,
        "created_at": sub.created_at,
        "disabled_at": sub.disabled_at,
    }


def delete_subscription(session: Session, subscription_id: str) -> None:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise LookupError("subscription not found")
    session.delete(sub)
    session.commit()


def list_deliveries(session: Session, subscription_id: str, limit: int = 50) -> list[WebhookDelivery]:
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == subscription_id)
        .order_by(WebhookDelivery.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    return list(session.exec(stmt))


# --- delivery ---------------------------------------------------------------


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _http_post(url: str, body: bytes, headers: dict, timeout: int) -> tuple[Optional[int], Optional[str]]:
    """POST the signed body. Returns (status_code, error). Best-effort: any network
    failure returns (None, reason) rather than raising."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — http(s) enforced at create
            return resp.status, None
    except urllib.error.HTTPError as exc:  # a real HTTP status (4xx/5xx)
        return exc.code, None
    except Exception as exc:  # noqa: BLE001 — connection/timeout/etc. are best-effort
        return None, type(exc).__name__


def _deliver(delivery_id: str, engine) -> None:
    """Worker: sign + POST one delivery, record the outcome, auto-disable on a
    failure streak. Opens its own session on the captured engine."""
    with Session(engine) as s:
        d = s.get(WebhookDelivery, delivery_id)
        if d is None:
            return
        sub = s.get(WebhookSubscription, d.subscription_id)
        if sub is None:
            d.status, d.error = "failed", "subscription missing"
            s.add(d)
            s.commit()
            return
        try:
            secret = webhook_crypto.decrypt(sub.secret_enc)
        except Exception:  # noqa: BLE001 — never leak crypto internals
            d.status, d.error = "failed", "secret decrypt failed"
            s.add(d)
            s.commit()
            return
        body = d.request_body.encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Approvo-Webhooks/1",
            "X-Approvo-Event": d.event_kind,
            "X-Approvo-Delivery": d.id,
            "X-Approvo-Signature": f"sha256={_sign(secret, body)}",
        }
        status_code, error = _http_post(sub.target_url, body, headers, _TIMEOUT_SECONDS)
        d.status_code = status_code
        d.delivered_at = now_utc()
        if error is None and status_code is not None and 200 <= status_code < 300:
            d.status, d.error = "delivered", None
            sub.failure_count = 0
        else:
            d.status = "failed"
            d.error = (error or f"HTTP {status_code}")[:500]
            sub.failure_count += 1
            if sub.failure_count >= _FAILURE_THRESHOLD:
                sub.enabled = False
                sub.disabled_at = now_utc()
        s.add(d)
        s.add(sub)
        s.commit()


def _queue_delivery(session: Session, sub_id: str, *, kind: str, event_id: Optional[str], body: str, attempt: int = 1) -> WebhookDelivery:
    d = WebhookDelivery(
        id=new_id("whd"),
        subscription_id=sub_id,
        event_kind=kind,
        event_id=event_id,
        request_body=body,
        status="pending",
        attempt=attempt,
        created_at=now_utc(),
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    _submit(_deliver, d.id, session.get_bind())
    return d


def redeliver(session: Session, delivery_id: str) -> WebhookDelivery:
    old = session.get(WebhookDelivery, delivery_id)
    if old is None:
        raise LookupError("delivery not found")
    return _queue_delivery(
        session, old.subscription_id, kind=old.event_kind,
        event_id=old.event_id, body=old.request_body, attempt=old.attempt + 1,
    )


def send_test(session: Session, subscription_id: str) -> WebhookDelivery:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise LookupError("subscription not found")
    envelope = {
        "id": new_id("evt"),
        "kind": "webhook.test",
        "occurred_at": now_utc(),
        "actor_id": actor.current_actor_id(),
        "workspace_id": sub.workspace_id,
        "project_id": None,
        "entity": {"type": "webhook", "id": sub.id, "snapshot": {"message": "test delivery"}},
    }
    return _queue_delivery(
        session, sub.id, kind="webhook.test", event_id=envelope["id"], body=json.dumps(envelope)
    )


# --- audit-driven trigger (no new event bus) --------------------------------


def _kind(a: AuditEvent) -> str:
    return f"{a.entity_type}.{a.event_type}"


def _envelope_from_audit(a: AuditEvent) -> dict:
    payload = None
    if a.payload_json:
        try:
            payload = json.loads(a.payload_json)
        except (json.JSONDecodeError, TypeError):
            payload = None
    return {
        "id": a.id,
        "kind": _kind(a),
        "occurred_at": a.created_at,
        "actor_id": a.actor_id,
        "workspace_id": a.workspace_id,
        "project_id": a.project_id,
        "entity": {"type": a.entity_type, "id": a.entity_id, "snapshot": payload},
    }


def _matches(sub: WebhookSubscription, env: dict) -> bool:
    kinds = json.loads(sub.event_kinds_json or "[]")
    if kinds and env["kind"] not in kinds:
        return False
    projects = json.loads(sub.project_ids_json or "[]")
    if projects and env.get("project_id") not in projects:
        return False
    return True


def _dispatch(engine, env: dict) -> None:
    with Session(engine) as s:
        workspace_id = env.get("workspace_id")
        if workspace_id is None and env.get("project_id"):
            proj = s.get(Project, env["project_id"])
            workspace_id = proj.workspace_id if proj else None
        if workspace_id is None:
            return
        subs = s.exec(
            select(WebhookSubscription).where(
                WebhookSubscription.workspace_id == workspace_id,
                WebhookSubscription.enabled == True,  # noqa: E712 — SQL boolean
            )
        ).all()
        body = json.dumps(env)
        for sub in subs:
            if _matches(sub, env):
                _queue_delivery(s, sub.id, kind=env["kind"], event_id=env["id"], body=body)


@event.listens_for(Session, "before_commit")
def _collect_events(session: Session) -> None:
    # Capture eligible audit events while their attributes are still loaded. Inert
    # (and thus test-neutral) unless webhook encryption is configured.
    if not webhook_crypto.is_enabled():
        return
    pending = [
        _envelope_from_audit(obj)
        for obj in session.new
        if isinstance(obj, AuditEvent) and obj.entity_type in WEBHOOK_ENTITY_TYPES
    ]
    if pending:
        session.info["_wh_pending"] = (session.info.get("_wh_pending") or []) + pending


@event.listens_for(Session, "after_commit")
def _fire_events(session: Session) -> None:
    pending = session.info.pop("_wh_pending", None)
    if not pending:
        return
    engine = session.get_bind()
    for env in pending:
        try:
            _dispatch(engine, env)
        except Exception:  # noqa: BLE001 — delivery is best-effort, never break the request
            pass
