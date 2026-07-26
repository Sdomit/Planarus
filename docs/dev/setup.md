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
./run-planarus.sh        # macOS / Linux
run-planarus.bat      # Windows
```

Either one checks your venv and pnpm, runs `alembic upgrade head`, starts the
API and the Vite dev server, waits until both actually answer, then opens the
UI. If 8000 or 5173 is busy it picks the next free port and passes it through
everywhere. Local dev only — the external API stays disabled.

On Windows, `run-planarus.bat` also creates `apps/api/.venv` with Python 3.11
and installs the local API/web dependencies if they are missing. It exits
nonzero instead of opening a broken UI when bootstrap, migration, API health,
or web readiness fails. A plain run explicitly keeps the app anonymous, even
if the parent shell previously enabled team-mode variables.

Use the optional verification mode before a handoff or after a larger change:

```powershell
run-planarus.bat verify
```

It runs the complete API pytest suite and the web Vitest, typecheck, and
production-build checks before it starts the local app. Add `team` only when
you explicitly want local sign-in: `run-planarus.bat team verify`.

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
python3 scripts/seed_planarus_project.py
```

Kept in sync with `context/NEXT_STEP.md` each slice.

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
