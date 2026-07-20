---
project: approvo
kind: guide
updated_at: 2026-07-19
source_of_truth: Approvo
---

# Notifications & backups

How to make Approvo chase your deadlines, protect its database, and get that
database back. Everything here is **off by default** and local — no data leaves
your machine unless you point it somewhere that syncs.

Both halves share one idea: **Approvo runs no background scheduler.** It ships a
command; your operating system decides when to run it. That way a reminder still
fires when the app is closed, nothing double-fires when the API runs more than
one worker, and the very same command is what a hosted cron job would call.

## Scheduled reminders

The **in-app feed** (the bell) needs no setup at all — it is computed live from
your approvals, due tasks, and open blockers every time you look at it.

**Email reminders** are the part that must be scheduled, because a due date
passing is not an event anything can react to. Nobody edits the task; no webhook
fires. Something has to go and look.

### 1. Turn email on

Email is off by default and only ever sends to a **loopback SMTP host** — a local
Mailpit, never a relay. In **Settings**, switch **Email** on and set the From
address.

### 2. Add a rule to a project

Each rule is one recipient plus a trigger:

| Trigger | Sends |
|---|---|
| `due_soon` | overdue tasks, plus anything due inside the threshold (default 48h) |
| `daily_digest` | open tasks, open blockers, pending proposals, and what is due |

A rule with nothing to report sends nothing. A digest of zeroes is how people
learn to filter your mail.

### 3. Let the OS run it

```bash
cd apps/api
python -m app.jobs reminders
```

That walks every active project and sends what its rules ask for. Archived
projects are left alone. It is safe to run as often as you like: nothing due
means nothing sent, and the per-project daily cap (20) bounds the worst case.

Now put it on a schedule. **cron** (Linux/macOS) — every morning at 08:00:

```cron
0 8 * * * cd /path/to/approvo/apps/api && /path/to/.venv/bin/python -m app.jobs reminders
```

Plain cron does **not** catch up a run it missed while the machine was off. If
that matters, use a **systemd timer** instead and set `Persistent=true`, which
runs the job on the next boot after a missed window:

```ini
# ~/.config/systemd/user/approvo-reminders.timer
[Timer]
OnCalendar=08:00
Persistent=true
```

On **Windows Task Scheduler**, the equivalent is the trigger option *"Run task as
soon as possible after a scheduled start is missed"*. A laptop that sleeps
through 08:00 is the normal case, not the edge case — turn this on.

### What the exit codes mean

The command prints one line and returns a code, so a scheduler can tell the
difference between "quiet" and "broken":

| Code | Meaning |
|---|---|
| `0` | ran fine — mail sent, or legitimately nothing was due |
| `1` | something genuinely failed (SMTP refused, a message was withheld) — **look at this** |
| `2` | refused on purpose: email is switched off |

A job that exits `1` every morning is a broken pipeline telling you so. That is
the whole reason it does not just exit `0` and stay quiet.

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

1. **Settings → Integrations → Backups**, switch **Enable backups** on (it is off
   by default — a backup writes files outside the database).
2. Optionally set **Keep last N** (default 7). Older backups beyond N are pruned;
   only files Approvo generated are ever deleted.
3. Point the destination where you want it:
   ```bash
   AGENTBOARD_BACKUP_DIR=/path/to/somewhere   # default ./agentboard-backups
   ```

> **A backup on the same disk is not a backup strategy.** It protects you from a
> bad migration or a mistaken delete — not from losing the disk, the laptop, or
> the machine to ransomware.

### Getting a copy off this machine

Two ways. Pick whichever you already have:

- **A synced folder — simplest, no extra setting.** Point `AGENTBOARD_BACKUP_DIR`
  at OneDrive, Dropbox, or an rclone mount. That is the entire change.
- **Object storage.** Tick **Also copy each backup off-site**. This reuses the
  storage backend, so it needs `AGENTBOARD_STORAGE_BACKEND=s3` plus the
  `AGENTBOARD_S3_*` settings and the `[s3]` extra. On the default `local` backend
  the switch is disabled on purpose: pushing there would write the copy beside
  the original, which protects nothing.

The push runs **after** the snapshot passes its integrity check, and it is
best-effort by design. If the upload fails you still have a good, verified local
backup, and the UI says the off-site copy did not happen and why. A degraded
backup you know about beats a silent one.

Backups are SQLite-only. On Postgres the button refuses and tells you to use
`pg_dump` or your platform's managed snapshots + point-in-time recovery, which
do the job better than anything shipped here would.

## Taking a backup

- **Settings → backups → Back up now**,
- `POST /api/v1/backups` (local, control-token + server-admin gated), or
- `python -m app.jobs backup` — the same CLI as reminders, so it goes on the same
  scheduler. A nightly backup next to a morning reminder run is a sensible
  default. Same exit codes: `2` means backups are switched off, `1` means a
  snapshot was actually attempted and failed.

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
