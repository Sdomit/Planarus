"""Operational CLI (Phase 18 — D41, D43).

One entrypoint carries two kinds of subcommand, so there is exactly one thing to
schedule and one thing to run by hand:

* **scheduled** — invoked by the OS scheduler (cron, Task Scheduler, a systemd
  timer). Per D41 Approvo deliberately has no in-process scheduler: the cadence
  belongs to the platform, and this module is what the platform calls. The same
  command is what a hosted CronJob would invoke.
* **operator** — ``verify`` and ``restore``, run by a human with the app stopped.
  Restore is a CLI command and never an HTTP route (D43): swapping the database
  file under a running app is a corruption path, not a feature.

Every subcommand prints one line and returns a shell exit code — **0 success,
non-zero failure** — so a scheduler surfaces a failed run instead of silently
recording success.

    python -m app.jobs verify [NAME]
    python -m app.jobs restore NAME --yes
"""
from __future__ import annotations

import argparse
import sys

from app.core.exceptions import ConflictError
from app.services import backup_service

# Refusing a destructive action without explicit confirmation is a distinct
# outcome from "it failed" — a scheduler/operator can tell them apart.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


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
