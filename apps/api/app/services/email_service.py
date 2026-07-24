"""Scoped email reminders (Phase 9): local SMTP (Mailpit) only, manual send.

Boundaries, in order of enforcement:

1. Disabled by default — ``PLANARUS_EMAIL_ENABLED=true`` is required.
2. Loopback SMTP only — the configured host must be 127.0.0.1/::1/localhost, so
   Planarus can never become an outbound relay. Hosted providers (Brevo,
   Resend) are a later, explicitly designed phase.
3. Per-project daily send cap (anti-abuse, counted from EmailLog).
4. Fail-closed secret scan on subject+body before anything leaves the process.
5. The body is never stored or logged — EmailLog keeps recipient/subject/status.

There is no scheduler: sends are human-triggered ("send now") from the local UI.
"""
import smtplib
from email.message import EmailMessage

from sqlmodel import Session, select

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc
from app.models.approval_request import ApprovalRequest
from app.models.blocker import Blocker
from app.models.email_log import EmailLog
from app.models.notification_rule import NotificationRule
from app.models.project import Project
from app.models.task import Task
from app.prompt.secrets import scan
from app.services.audit_service import create_audit_event
from app.services import status_option_service
from app.services.notification_service import due_task_buckets
from app.services.settings_service import get_setting
from app.schemas.notifications import ReminderOutcome, ReminderSendResult

# ponytail: fixed daily cap; make it a setting if a real use case ever needs more.
EMAIL_DAILY_CAP = 20

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_SMTP_TIMEOUT_SECONDS = 5.0


def _sent_today(session: Session, project_id: str) -> int:
    today = now_utc()[:10]  # ISO date prefix; sent_at is ISO-8601 UTC
    return len(
        session.exec(
            select(EmailLog)
            .where(EmailLog.project_id == project_id)
            .where(EmailLog.status == "sent")
            .where(EmailLog.sent_at >= today)  # type: ignore[arg-type]
        ).all()
    )


def _due_soon_body(session: Session, project: Project, rule: NotificationRule) -> str | None:
    overdue, due_soon = due_task_buckets(session, project.id, rule.threshold_hours)
    if not overdue and not due_soon:
        return None
    lines = [f"Planarus reminders for project: {project.title}", ""]
    if overdue:
        lines.append(f"Overdue tasks ({len(overdue)}):")
        lines.extend(f"  - {t.title} (due {t.due_at})" for t in overdue)
        lines.append("")
    if due_soon:
        lines.append(f"Due within {rule.threshold_hours}h ({len(due_soon)}):")
        lines.extend(f"  - {t.title} (due {t.due_at})" for t in due_soon)
        lines.append("")
    lines.append("— Planarus (local)")
    return "\n".join(lines)


def _digest_body(session: Session, project: Project, rule: NotificationRule) -> str:
    tasks = session.exec(select(Task).where(Task.project_id == project.id)).all()
    # #88: the digest's counts follow the project's own status categories, so a
    # board with a custom "Shipped" column doesn't report its finished work as
    # still open (and as zero done).
    categories = status_option_service.status_categories(session, project.id, "task")
    open_tasks = [t for t in tasks if categories.get(t.status, "open") == "open"]
    done = sum(1 for t in tasks if categories.get(t.status) == "done")
    blockers = session.exec(
        select(Blocker)
        .where(Blocker.project_id == project.id)
        .where(Blocker.status == "open")
    ).all()
    pending = session.exec(
        select(ApprovalRequest)
        .where(ApprovalRequest.project_id == project.id)
        .where(ApprovalRequest.status == "pending")
    ).all()
    overdue, due_soon = due_task_buckets(session, project.id, rule.threshold_hours)

    lines = [
        f"Planarus daily digest for project: {project.title}",
        "",
        f"Open tasks: {len(open_tasks)} (done: {done})",
        f"Open blockers: {len(blockers)}",
        f"Pending agent proposals: {len(pending)}",
        f"Overdue tasks: {len(overdue)}; due within {rule.threshold_hours}h: {len(due_soon)}",
    ]
    if overdue:
        lines.append("")
        lines.append("Overdue:")
        lines.extend(f"  - {t.title} (due {t.due_at})" for t in overdue)
    lines.extend(["", "— Planarus (local)"])
    return "\n".join(lines)


def _log(
    session: Session,
    project_id: str,
    rule: NotificationRule,
    subject: str,
    status: str,
    error: str | None = None,
) -> EmailLog:
    log = EmailLog(
        id=new_id("eml"),
        project_id=project_id,
        rule_id=rule.id,
        to_email=rule.to_email,
        subject=subject,
        status=status,
        error=error,
        sent_at=now_utc(),
        created_at=now_utc(),
    )
    session.add(log)
    session.flush()
    return log


def send_project_reminders(session: Session, project_id: str) -> ReminderSendResult:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError(f"project '{project_id}' not found")

    # Live switch (DB row) within the env default — a UI toggle takes effect
    # without a restart; env-only deployments (no row) behave exactly as before.
    if not get_setting(session, "email_enabled", settings.email_enabled):
        raise ConflictError(
            "email sending is disabled — enable it in Settings or set "
            "PLANARUS_EMAIL_ENABLED=true (local Mailpit only)"
        )
    if settings.smtp_host.strip().lower() not in _LOOPBACK_HOSTS:
        raise ConflictError(
            "email reminders only send to a loopback SMTP host (Mailpit); "
            "remote SMTP is not supported"
        )

    rules = [
        r
        for r in session.exec(
            select(NotificationRule)
            .where(NotificationRule.project_id == project_id)
            .order_by(NotificationRule.created_at, NotificationRule.id)
        ).all()
        if r.enabled and r.channel == "email"
    ]

    outcomes: list[ReminderOutcome] = []
    sent_today = _sent_today(session, project_id)  # once; incremented per send below
    for rule in rules:
        if sent_today >= EMAIL_DAILY_CAP:
            outcomes.append(
                ReminderOutcome(
                    rule_id=rule.id, status="skipped", reason="daily email cap reached"
                )
            )
            continue

        if rule.trigger_type == "due_soon":
            body = _due_soon_body(session, project, rule)
            if body is None:
                outcomes.append(
                    ReminderOutcome(
                        rule_id=rule.id, status="skipped", reason="nothing due"
                    )
                )
                continue
            subject = f"[Planarus] {project.title} — task reminders"
        else:  # daily_digest
            body = _digest_body(session, project, rule)
            subject = f"[Planarus] {project.title} — daily digest"

        # Fail closed: never send content that looks like it carries a secret.
        if scan(subject + "\n" + body, source_ref=f"email:{rule.id}"):
            log = _log(session, project_id, rule, subject, "failed",
                       "secret-like content detected; email not sent")
            outcomes.append(
                ReminderOutcome(
                    rule_id=rule.id,
                    status="failed",
                    reason="secret-like content detected; email not sent",
                    email_log_id=log.id,
                )
            )
            continue

        msg = EmailMessage()
        msg["From"] = get_setting(session, "email_from", settings.email_from)
        msg["To"] = rule.to_email
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS
            ) as smtp:
                smtp.send_message(msg)
        except Exception as exc:  # noqa: BLE001 — record, never crash the endpoint
            log = _log(session, project_id, rule, subject, "failed",
                       f"{type(exc).__name__}: {exc}"[:500])
            outcomes.append(
                ReminderOutcome(
                    rule_id=rule.id,
                    status="failed",
                    reason=f"{type(exc).__name__}: {exc}"[:200],
                    email_log_id=log.id,
                )
            )
            continue

        sent_today += 1
        log = _log(session, project_id, rule, subject, "sent")
        create_audit_event(
            session,
            event_type="email_send",
            actor_type="human",
            entity_type="email_log",
            entity_id=log.id,
            project_id=project_id,
        )
        outcomes.append(
            ReminderOutcome(rule_id=rule.id, status="sent", email_log_id=log.id)
        )

    session.commit()
    return ReminderSendResult(
        project_id=project_id,
        sent=sum(1 for o in outcomes if o.status == "sent"),
        skipped=sum(1 for o in outcomes if o.status == "skipped"),
        failed=sum(1 for o in outcomes if o.status == "failed"),
        outcomes=outcomes,
    )


def list_email_log(session: Session, project_id: str, limit: int = 50) -> list[EmailLog]:
    stmt = (
        select(EmailLog)
        .where(EmailLog.project_id == project_id)
        .order_by(EmailLog.sent_at.desc(), EmailLog.id.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    return list(session.exec(stmt).all())
