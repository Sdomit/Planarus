"""Operational CLI (Phase 18 — D41, D43).

One entrypoint carries two kinds of subcommand, so there is exactly one thing to
schedule and one thing to run by hand:

* **scheduled** — ``reminders`` and ``backup``, invoked by the OS scheduler
  (cron, Task Scheduler, a systemd timer). Per D41 Approvo deliberately has no
  in-process scheduler: the cadence belongs to the platform, and this module is
  what the platform calls. The same command is what a hosted CronJob would
  invoke. Both are safe to run repeatedly — ``reminders`` skips what is not due
  and is bounded by the per-project daily cap, ``backup`` prunes to the retention
  setting.
* **operator** — ``verify`` and ``restore``, run by a human with the app stopped.
  Restore is a CLI command and never an HTTP route (D43): swapping the database
  file under a running app is a corruption path, not a feature.

Every subcommand prints one line and returns a shell exit code — **0 success,
1 failure, 2 refused** — so a scheduler surfaces a failed run instead of silently
recording success, and can tell "switched off on purpose" apart from "broken".

    python -m app.jobs reminders
    python -m app.jobs backup
    python -m app.jobs verify [NAME]
    python -m app.jobs restore NAME --yes
"""
from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from collections.abc import Iterator

from sqlmodel import Session, select

from app.core.exceptions import ConflictError
from app.models.project import Project
from app.services import backup_service, email_service, settings_service

# Refusing a destructive action without explicit confirmation is a distinct
# outcome from "it failed" — a scheduler/operator can tell them apart.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


@contextmanager
def _session() -> Iterator[Session]:
    """Open a database session for a CLI run.

    There is no FastAPI dependency injection here, so this is the single seam the
    tests replace. The engine import is deliberately lazy: ``verify`` and
    ``restore`` touch only files and run with the app stopped, and must not build
    an engine against a database that is mid-swap.
    """
    from app.db.session import engine

    with Session(engine) as session:
        yield session


# --- scheduled (D41: the OS scheduler calls these) -----------------------------


def _cmd_reminders(args: argparse.Namespace) -> int:
    with _session() as session:
        projects = list(
            session.exec(
                select(Project).where(Project.archived_at.is_(None))  # type: ignore[union-attr]
            ).all()
        )
        sent = skipped = failed = 0
        for project in projects:
            try:
                result = email_service.send_project_reminders(session, project.id)
            except ConflictError as exc:
                # This gate is global (email switched off, or a non-loopback SMTP
                # host), not per-project — every remaining project would refuse
                # identically, so stop rather than repeat the same message N times.
                print(f"reminders: {exc.detail}", file=sys.stderr)
                return EXIT_REFUSED
            sent += result.sent
            skipped += result.skipped
            failed += result.failed

        print(
            f"reminders: {len(projects)} project(s); "
            f"sent {sent}, skipped {skipped}, failed {failed}"
        )
        # Individual rules fail without raising (SMTP refused the message,
        # secret-like content was caught). Those must still exit non-zero, or a
        # silently broken reminder pipeline reports success to cron forever.
        return EXIT_FAILED if failed else EXIT_OK


def _cmd_backup(args: argparse.Namespace) -> int:
    with _session() as session:
        # Checked here rather than left to create_backup so that "switched off"
        # exits 2 (refused) while a real failure — a snapshot that fails its
        # integrity check, an unsupported engine — still raises ConflictError and
        # exits 1. Collapsing both onto one code would hide genuine breakage.
        if not settings_service.backup_enabled(session):
            print(
                "backup: disabled — enable backups in Settings "
                "(a backup writes files outside the database, so it is opt-in)",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        result = backup_service.create_backup(session)
        print(
            f"backup: {result.backup.name} "
            f"({result.backup.size_bytes} bytes, pruned {result.pruned})"
        )
        return EXIT_OK


# --- operator (app stopped) ----------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    name = args.name
    if name is None:
        existing = backup_service.list_backups()
        if not existing:
            print("verify: no backups found", file=sys.stderr)
            return EXIT_FAILED
        name = existing[0].name  # newest
    backup_service.verify_backup(name)
    print(f"verify: {name} OK")
    return EXIT_OK


def _cmd_restore(args: argparse.Namespace) -> int:
    if not args.yes:
        print(
            "restore: refusing without --yes — this replaces the live database; "
            "stop the app first",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    result = backup_service.restore_backup(args.name)
    kept = ", ".join(result.displaced) or "nothing to displace"
    print(
        f"restore: {result.restored_from} -> {result.database} "
        f"(previous state kept as: {kept})"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.jobs",
        description="Approvo operational commands (scheduled jobs + operator tools).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    reminders = sub.add_parser(
        "reminders", help="send due email reminders for every active project"
    )
    reminders.set_defaults(func=_cmd_reminders)

    backup = sub.add_parser("backup", help="take one verified database backup")
    backup.set_defaults(func=_cmd_backup)

    verify = sub.add_parser(
        "verify", help="integrity-check a backup (default: the newest one)"
    )
    verify.add_argument("name", nargs="?", help="backup file name; omit for newest")
    verify.set_defaults(func=_cmd_verify)

    restore = sub.add_parser(
        "restore",
        help="replace the live database with a backup (stop the app first)",
    )
    restore.add_argument("name", help="backup file name")
    restore.add_argument(
        "--yes", action="store_true", help="confirm this destructive action"
    )
    restore.set_defaults(func=_cmd_restore)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConflictError as exc:
        print(f"{args.command}: {exc.detail}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
