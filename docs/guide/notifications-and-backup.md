---
project: approvo
kind: guide
updated_at: 2026-07-19
source_of_truth: Approvo
---

# Backups & restore

How to protect the Approvo database and get it back. Everything here is **off by
default** and local — no data leaves your machine unless you point it somewhere
that syncs.

> **Scheduled email reminders** (the other half of Phase 18) arrive with slice
> 18.1. This guide covers what is built today: backups and restore.

## What a backup is here

One consistent snapshot of the whole SQLite database, written with SQLite's own
`VACUUM INTO` and then **checked with `PRAGMA integrity_check`** before it counts.
If the check fails the file is deleted rather than left looking restorable.

This is **not** the same as project export (Settings → Integrations → Export):

| | Backup | Export (17.6) |
|---|---|---|
| Scope | the entire database | one project's planning graph |
| Fidelity | faithful — same ids, same history | lossy by design: no audit history, approvals, email logs, context files, notification rules, agent runs; **ids are remapped on import** |
| Use it to | survive a disk, a bad migration, a fat-finger delete | move a project to another instance |

Use export to move work. Use backup to survive a bad day.

## Turning backups on

1. **Settings → backups**, switch **Enable backups** on (it is off by default —
   a backup writes files outside the database).
2. Optionally set **Keep last N** (default 7). Older backups beyond N are pruned;
   only files Approvo generated are ever deleted.
3. Optionally point the destination somewhere off this disk:
   ```bash
   AGENTBOARD_BACKUP_DIR=/path/to/somewhere   # default ./agentboard-backups
   ```

> **A backup on the same disk is not a backup strategy.** It protects you from a
> bad migration or a mistaken delete, not from losing the disk, the laptop, or
> the machine to ransomware. Point `AGENTBOARD_BACKUP_DIR` at a synced folder
> (OneDrive, Dropbox, an rclone mount) so a copy lives somewhere else. That is
> the whole change — no extra setting.

Backups are SQLite-only. On Postgres the button refuses and tells you to use
`pg_dump` or your platform's managed snapshots + point-in-time recovery, which
do the job better than anything shipped here would.

## Taking a backup

- **Settings → backups → Back up now**, or
- `POST /api/v1/backups` (local, control-token + server-admin gated).

**Take one before every `alembic upgrade`.** It is the cheapest insurance that
exists against the worst case.

## Checking a backup

```bash
cd apps/api
python -m app.jobs verify              # the newest backup
python -m app.jobs verify agentboard-20260719T220501123456Z.db
```

Exit code `0` means it passed. A failing backup is **not** deleted by `verify` —
a suspect copy may still be the best one you have.

## Restoring (the drill)

Restore is a command, never a button. Swapping the database file under a running
app is a corruption path, so:

```bash
# 1. STOP the app first. This is not optional.
cd apps/api
python -m app.jobs restore agentboard-20260719T220501123456Z.db --yes
# 2. Start the app again.
```

What it does, in this order:

1. **Verifies the backup first** — a corrupt backup can never overwrite good data.
2. Moves the current database *and its `-wal`/`-shm` sidecars* aside as
   `.pre-restore-<timestamp>` files. A stale WAL left next to a restored database
   can be replayed over it; that is why the sidecars move too. It also means a
   mistaken restore is reversible — your previous state is still on disk.
3. Copies the backup into place and re-checks that what landed is intact.

Without `--yes` it refuses and changes nothing (exit code `2`).

### Rehearse it

A restore you have never run is a hope, not a plan. Do this once on a copy:
back up, restore, open the app, confirm your projects are there. The same round
trip runs in CI on every push (`tests/test_restore.py`), so the mechanism cannot
rot silently — but rehearsing *your* setup is still worth ten minutes.

### If a restore fails

The error names the `.pre-restore-<timestamp>` files holding your previous state.
Rename the main one back to the database filename (dropping the
`.pre-restore-…` suffix) and you are where you started.
