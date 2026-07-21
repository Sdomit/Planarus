"""Outbound webhook management (Phase 17.3, D38).

Workspace-owner + local-control-token gated (like api-clients: a workspace-scoped
integration resource, so owner-gated rather than server-admin — see the D35
as-built note). The whole surface 404s when webhook encryption is unconfigured
(``PLANARUS_WEBHOOK_ENC_KEY`` unset) — indistinguishable from "no such route".
The signing secret is returned exactly once (create) and never in any read.
Deliveries are outbound read/notify only — a webhook never approves or applies.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core import tenant, webhook_crypto
from app.core.config import settings
from app.core.security import require_local_control
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryRead,
    WebhookRead,
)
from app.services import webhook_service

router = APIRouter()


def _require_enabled() -> None:
    if not webhook_crypto.is_enabled():
        raise HTTPException(status_code=404, detail="the requested resource was not found")


def _guard(session: Session, workspace_id: str, user: Optional[User]) -> None:
    if settings.auth_enabled:
        tenant.require_workspace_access(session, workspace_id, user, *tenant.APPROVER_ROLES)


def _load_sub(session: Session, subscription_id: str) -> WebhookSubscription:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub


@router.get("/webhooks", response_model=list[WebhookRead], dependencies=[Depends(require_local_control)])
def list_webhooks(
    workspace_id: Optional[str] = None,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[WebhookRead]:
    _require_enabled()
    if settings.auth_enabled:
        if workspace_id is None:
            raise HTTPException(status_code=400, detail="workspace_id is required")
        _guard(session, workspace_id, user)
    return [
        WebhookRead(**webhook_service.to_read(s))
        for s in webhook_service.list_subscriptions(session, workspace_id)
    ]


@router.post("/webhooks", response_model=WebhookCreated, status_code=201, dependencies=[Depends(require_local_control)])
def create_webhook(
    payload: WebhookCreate,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> WebhookCreated:
    _require_enabled()
    _guard(session, payload.workspace_id, user)
    try:
        sub, secret = webhook_service.create_subscription(
            session,
            workspace_id=payload.workspace_id,
            target_url=payload.target_url,
            event_kinds=payload.event_kinds,
            project_ids=payload.project_ids,
            fmt=payload.format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return WebhookCreated(subscription=WebhookRead(**webhook_service.to_read(sub)), secret=secret)


@router.delete("/webhooks/{subscription_id}", status_code=204, dependencies=[Depends(require_local_control)])
def delete_webhook(
    subscription_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> None:
    _require_enabled()
    sub = _load_sub(session, subscription_id)
    _guard(session, sub.workspace_id, user)
    webhook_service.delete_subscription(session, subscription_id)


@router.get(
    "/webhooks/{subscription_id}/deliveries",
    response_model=list[WebhookDeliveryRead],
    dependencies=[Depends(require_local_control)],
)
def list_webhook_deliveries(
    subscription_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[WebhookDeliveryRead]:
    _require_enabled()
    sub = _load_sub(session, subscription_id)
    _guard(session, sub.workspace_id, user)
    return [
        WebhookDeliveryRead.model_validate(d)
        for d in webhook_service.list_deliveries(session, subscription_id)
    ]


@router.post(
    "/webhooks/{subscription_id}/test",
    response_model=WebhookDeliveryRead,
    status_code=202,
    dependencies=[Depends(require_local_control)],
)
def test_webhook(
    subscription_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> WebhookDeliveryRead:
    _require_enabled()
    sub = _load_sub(session, subscription_id)
    _guard(session, sub.workspace_id, user)
    return WebhookDeliveryRead.model_validate(webhook_service.send_test(session, subscription_id))


@router.post(
    "/webhooks/deliveries/{delivery_id}/redeliver",
    response_model=WebhookDeliveryRead,
    status_code=202,
    dependencies=[Depends(require_local_control)],
)
def redeliver_webhook(
    delivery_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> WebhookDeliveryRead:
    _require_enabled()
    existing = session.get(WebhookDelivery, delivery_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    sub = session.get(WebhookSubscription, existing.subscription_id)
    if sub is not None:
        _guard(session, sub.workspace_id, user)
    return WebhookDeliveryRead.model_validate(webhook_service.redeliver(session, delivery_id))
