"""Operational CLI (Phase 18 — D41, D43).

One entrypoint carries two kinds of subcommand, so there is exactly one thing to
schedule and one thing to run by hand:

* **scheduled** — ``reminders`` and ``backup``, invoked by the OS scheduler
  (cron, Task Scheduler, a systemd timer). Per D41 Planarus deliberately has no
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
    python -m app.jobs admin --list | --grant EMAIL | --reset-password EMAIL
    python -m app.jobs adopt-roots [--apply]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from contextlib import contextmanager
from collections.abc import Iterator

from sqlmodel import Session, select

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.fsmemory.project_root import ProjectRootError, managed_base, managed_root_for
from app.models.project import Project
from app.models.user import User
from app.services import admin_service, backup_service, email_service, settings_service

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


# --- operator: account recovery (D53) ------------------------------------------


def _cmd_admin(args: argparse.Namespace) -> int:
    """Get back into a server nobody can sign in to.

    A CLI and never a route (D53, following D43): whoever can run this already
    has the database file and could edit the row by hand, so it adds convenience
    and not a trust boundary — where an HTTP recovery path would be permanent
    unauthenticated surface for a once-a-year need.
    """
    if not settings.auth_enabled:
        print(
            "admin: auth is disabled on this server — no accounts to administer",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    with _session() as session:
        if args.list:
            rows = admin_service.list_users(session)
            if not rows:
                print("admin: no accounts yet — the first sign-up claims the server")
                return EXIT_OK
            for user, last_seen, _memberships in rows:
                flags = ", ".join(
                    f
                    for f in (
                        "admin" if user.is_admin else "",
                        "" if user.is_active else "deactivated",
                    )
                    if f
                )
                print(f"{user.email}{'  [' + flags + ']' if flags else ''}"
                      f"  last seen: {last_seen or 'never'}")
            return EXIT_OK

        email = (args.grant or args.reset_password or "").strip().lower()
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            print(f"admin: no account for {email}", file=sys.stderr)
            return EXIT_FAILED

        if args.grant:
            admin_service.set_admin(session, user, True)
            print(f"admin: {user.email} is now a server admin")
            return EXIT_OK

        temp = admin_service.reset_password(session, user)
        print(f"admin: temporary password for {user.email}: {temp}")
        print("       shown once; they must change it at sign-in, and every "
              "existing session for that account is now signed out")
        return EXIT_OK


# --- operator: adopt existing folders under the managed base (#115, 115.4) -----


def _cmd_adopt_roots(args: argparse.Namespace) -> int:
    """Bring pre-existing project folders under PLANARUS_PROJECTS_ROOT.

    Auth-enabled deployments derive each project root as
    ``<base>/<workspace_id>/<project_id>`` (#115). Projects created before that,
    or imported, may still point elsewhere. For each such project this copies the
    folder to the managed location, verifies it, and rewrites ``folder_path``.

    Copy, not move — the original is left in place, so a run is reversible. Prints
    a plan and changes nothing unless ``--apply`` is given.
    """
    try:
        base = managed_base()  # raises if PLANARUS_PROJECTS_ROOT is unset/relative
    except ProjectRootError as exc:
        print(
            f"adopt-roots: {exc}. Set PLANARUS_PROJECTS_ROOT to the server-owned "
            "projects base first.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    with _session() as session:
        projects = list(
            session.exec(
                select(Project).where(Project.folder_path.is_not(None))  # type: ignore[union-attr]
            ).all()
        )
        pending = []
        for project in projects:
            target = managed_root_for(project.workspace_id, project.id)
            if os.path.realpath(project.folder_path) != target:
                pending.append((project, os.path.realpath(project.folder_path), target))

        if not pending:
            print(f"adopt-roots: nothing to do — every project root is already under {base}")
            return EXIT_OK

        if not args.apply:
            for project, src, target in pending:
                print(f"[dry-run] {project.id}: {src} -> {target}")
            print(f"adopt-roots: {len(pending)} project(s) would be adopted "
                  "(dry run; pass --apply to make changes)")
            return EXIT_OK

        adopted = failed = 0
        for project, src, target in pending:
            if os.path.exists(target):
                print(f"adopt-roots: {project.id}: target already exists, skipping: {target}",
                      file=sys.stderr)
                failed += 1
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, target)
                if not os.path.isdir(target):
                    print(f"adopt-roots: {project.id}: copy did not produce {target}",
                          file=sys.stderr)
                    failed += 1
                    continue
                note = f"copied {src} -> {target} (original kept)"
            else:
                note = f"source folder missing; repointed to {target}"
            project.folder_path = target
            session.add(project)
            adopted += 1
            print(f"[adopt] {project.id}: {note}")

        session.commit()
        print(f"adopt-roots: {adopted} adopted, {failed} skipped/failed, "
              f"{len(pending)} needed adoption")
        return EXIT_FAILED if failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.jobs",
        description="Planarus operational commands (scheduled jobs + operator tools).",
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

    admin = sub.add_parser(
        "admin",
        help="account recovery: list accounts, grant admin, reset a password",
    )
    # Exactly one action per run — "grant and also reset" is two decisions, and
    # a typo that silently did both would be a bad surprise on a recovery path.
    action = admin.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="list every account")
    action.add_argument("--grant", metavar="EMAIL", help="make this account a server admin")
    action.add_argument(
        "--reset-password",
        metavar="EMAIL",
        help="issue a one-time temp password and sign that account out everywhere",
    )
    admin.set_defaults(func=_cmd_admin)

    adopt = sub.add_parser(
        "adopt-roots",
        help="copy existing project folders under PLANARUS_PROJECTS_ROOT (#115)",
    )
    adopt.add_argument(
        "--apply", action="store_true", help="make changes (default: dry run)"
    )
    adopt.set_defaults(func=_cmd_adopt_roots)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConflictError as exc:
        print(f"{args.command}: {exc.detail}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
