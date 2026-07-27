---
kind: dev_guide
updated_at: 2026-07-20
phase: implementation (Phases 1–17 on main)
---

# Developer setup

> Just want to run it? [`docker compose up --build`](../../README.md#quickstart)
> needs none of this. Read on only if you want hot reload and the test suites.

## One-command launcher

From the repo root:

```bash
./scripts/run-planarus.sh        # macOS / Linux
scripts\run-planarus.bat      # Windows
```

Either one checks your venv and pnpm, runs `alembic upgrade head`, starts the
API and the Vite dev server, waits until both actually answer, then opens the
UI. If 8000 or 5173 is busy it picks the next free port and passes it through
everywhere. Local dev only — the external API stays disabled.

On Windows, `scripts\run-planarus.bat` also creates `apps/api/.venv` with Python 3.11
and installs the local API/web dependencies if they are missing. It exits
nonzero instead of opening a broken UI when bootstrap, migration, API health,
or web readiness fails. A plain run explicitly keeps the app anonymous, even
if the parent shell previously enabled team-mode variables.

Use the optional verification mode before a handoff or after a larger change:

```powershell
scripts\run-planarus.bat verify
```

It runs the complete API pytest suite and the web Vitest, typecheck, and
production-build checks before it starts the local app. Add `team` only when
you explicitly want local sign-in: `scripts\run-planarus.bat team verify`.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11 (see `apps/api/.python-version`) | [python.org](https://python.org) |
| Node.js | 20 (see `.nvmrc`) | [nodejs.org](https://nodejs.org) |
| pnpm | pinned by `packageManager` in `package.json` | `corepack enable` |

Use `corepack enable` rather than `npm install -g pnpm` — corepack reads the
pinned version from `package.json`, so you get the one this repo is tested
against instead of whatever is newest.

**Debian / Ubuntu** additionally need the venv module, which isn't bundled:

```bash
sudo apt install python3-venv
```

## Backend (apps/api)

> Run every backend command from `apps/api`. The SQLite path is relative to your
> shell's working directory, so running these from the repo root silently
> creates a second, empty database and every request then fails with
> `no such table`.

```bash
cd apps/api

# Create and activate a virtual environment.
# Use `python3` on macOS/Linux — plain `python` often doesn't exist there.
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Install runtime + dev dependencies
pip install -e ".[dev]"

# Apply DB migrations before the first boot (and after pulling new ones)
alembic upgrade head

# Run the API server
uvicorn app.main:app --reload --port 8000

# The API is now available at:
#   http://localhost:8000/health
#   http://localhost:8000/api/v1/info
#   http://localhost:8000/docs   (Swagger UI)
```

`uvicorn` runs in the foreground and does not return. **Open a second terminal
for the frontend** — or just use the launcher above, which handles both.

### Optional: load the Planarus project into the app (dogfooding)

Planarus tracks its own roadmap. After migrating, seed the running DB with the
live project so you can follow progress in the Roadmap / Task Board instead of
only the Markdown context pack. Idempotent (safe to re-run); honors
`PLANARUS_DATABASE_URL`:

```bash
# from apps/api, like every other backend command above
python3 scripts/seed_planarus_project.py
```

The milestone titles in that seed are maintained by hand and are a snapshot, not
a live feed — treat it as demo data rather than the current roadmap.

### The demo project (seeded for you on first launch)

The launchers run this one themselves, so a fresh install opens on a populated
cockpit instead of an empty dashboard. `run-planarus.bat` / `run-planarus.sh`
call it with `--auto` between `alembic upgrade head` and `uvicorn`.

It builds a throwaway **"Planarus Demo — How We Built Planarus"** project that
exercises the whole feature surface in one place:

| | |
| --- | --- |
| Planning graph | phases, stages, tasks, sub-tasks, checklists, nested todos |
| Knowledge | documents of every type, a nested doc tree, `@` mentions and the backlinks they derive, an Excalidraw canvas whose cards link back to real entities |
| Governance | decisions, risks, blockers, milestones, and a custom status for each of the five entity types that support them |
| Time | calendar events (all-day, daily, weekly, monthly), task due dates, milestone targets |
| AI surfaces | pending, applied and rejected approval proposals, agent-run telemetry, external API keys |
| Operations | notification rules, an email send log, the generated on-disk context pack |

Dates that a view filters on are computed relative to today, so the calendar
has events in it and the notifications bell has something in it whenever the
demo is seeded — not only in the month this script was written.

Run it by hand if you want it sooner, or on a database the launcher never
touched:

```bash
# from apps/api
python3 scripts/seed_demo_project.py
```

Idempotent twice over. The project is only created once, and a `demo_seeded`
marker in the `setting` table means **deleting the demo project does not bring
it back** on the next launch. To get it back after deleting it:

```bash
python3 scripts/seed_demo_project.py --force
```

To never seed it at all, set `PLANARUS_SEED_DEMO=0` before launching. It is
also skipped automatically in team/hosted mode (`PLANARUS_AUTH_ENABLED=true`),
where workspaces are claimed by an admin during bootstrap and a pre-owned demo
project would get in the way — run it by hand there if you want it.

Two things the demo deliberately leaves empty, because they cannot be faked
usefully: **team members and assignees** (local mode has no accounts, and
inventing some would interfere with the team-mode sign-up flow) and **external
calendar connections** (they need real Google/Microsoft OAuth). Webhook rows
are seeded only when `PLANARUS_WEBHOOK_ENC_KEY` is configured, and the seeded
subscription is created **disabled** so the demo never sends real outbound
traffic.

The demo's on-disk context pack is written under the app's own data directory
(`%LOCALAPPDATA%\Planarus\demo-project` on Windows,
`~/.local/share/planarus/demo-project` elsewhere) rather than anywhere in your
Documents. That folder is also `git init`ed with the generated pack as its first
commit, so the cockpit's read-only Repository card has a branch, a commit and a
working-tree state to show instead of "Folder is not a Git repository". Both
steps are best-effort: no Git on `PATH` just means an empty Repository card.
Delete that folder along with the project to clean up fully.

### Why you cannot point a project at the Planarus checkout

Setting a project's folder to the repository you are running Planarus from is
refused with `422 invalid folder_path: refusing the application directory`.
That is `app/fsmemory/project_root.py` working as intended. Containment is
checked with `commonpath` in **both** directions, so `apps/api` is refused and
so is any ancestor of it — including the repository root, which contains it. A
project root is a directory the app writes generated files into; letting that
overlap the running application would put its own source code inside a
generated-file tree. Point the project at the folder you actually want managed,
not at Planarus itself.

### The repo cockpit and its gated Git actions

The Cockpit's Repository panel reads live Git state from the project folder —
branches, working tree, needs-merge, open PRs via your own `gh`. Reads are
always on; the folder can be picked with **Browse** (a server-side,
directories-only listing, local mode only) or typed as an absolute path, both
in the Repository panel and on the New project form.

The mutations are separate, human-clicked, audited, and each behind its own
off-by-default flag:

```bash
PLANARUS_GIT_FETCH_ENABLED=true   # "Fetch now" — remote-tracking refs only
PLANARUS_GIT_WRITE_ENABLED=true   # "Commit all" and "Merge into <branch>"
```

Commit stages everything and commits with your message. Merge only offers
branches that trail the default branch while the default branch is checked
out; it refuses a dirty tree and aborts on conflict, so the repo is never left
half-merged — resolve real conflicts in your editor or terminal, where they
belong. Agents, MCP and the external API have no Git or filesystem path at
all, flags or no flags.

## Frontend (apps/web)

```bash
# from the repo root — pnpm resolves the workspace
pnpm install
pnpm dev:web

# The frontend is now available at:
#   http://localhost:5173
```

The dev server proxies `/api` to `http://localhost:8000`. If your API is on a
different port, point it there without editing any file:

```bash
VITE_API_TARGET=http://localhost:8001 pnpm dev:web
```

## Running tests

Both suites run in CI on every PR, along with typecheck, a production build, a
Postgres migration round-trip, and a Docker Compose smoke test.

```bash
# Backend — from apps/api
python3 -m pytest

# Frontend — from the repo root
pnpm test:web
pnpm typecheck:web
pnpm build:web
```

A few backend tests skip by design — a Windows symlink-privilege test and
integration tests that need a live service (e.g. real Mailpit).

> Expected pass counts aren't listed here on purpose — they went stale three
> times. Compare against the last CI run on `main` instead.

## What is intentionally NOT implemented yet

| Feature | Status |
|---------|--------|
| Opt-in ChatGPT exposure (go-live) | Phase 7C2b — human-gated, runbook only |
| Hosted / SaaS mode | Code-complete groundwork, not turned on |
| Tauri desktop packaging | Not started |
