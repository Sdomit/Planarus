---
kind: dev_guide
updated_at: 2026-07-15
phase: implementation (Phases 1–9 + 4b on main)
---

# Developer setup

## One-command launcher (Windows)

From the repo root, run [`run-agentboard.bat`](../../run-agentboard.bat): it
checks the venv + pnpm, runs `alembic upgrade head`, starts the API
(`uvicorn app.main:app --reload --port 8000`) and the web dev server
(`pnpm dev:web`, port 5173), then opens the UI. Local dev only — the external
API stays disabled.

## Prerequisites

| Tool | Minimum version | Install |
|------|-----------------|---------|
| Python | 3.11 | [python.org](https://python.org) |
| Node.js | 20 | [nodejs.org](https://nodejs.org) |
| pnpm | 9 | `npm install -g pnpm` |

## Backend (apps/api)

```bash
cd apps/api

# Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Install runtime + dev dependencies (editable install works since cfac8fb)
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

## Frontend (apps/web)

```bash
cd apps/web

# Install dependencies
pnpm install

# Start the dev server (hot-reload)
pnpm dev

# The frontend is now available at:
#   http://localhost:5173
```

## Running tests

### Backend

```bash
cd apps/api
python -m pytest
```

Expected output: **630 passed, 2 skipped** (the skips are a Windows
symlink-privilege test and the real-Mailpit email integration test).

### Frontend

```bash
cd apps/web
pnpm test
```

Expected output: **77 tests pass**.

### Frontend typecheck

```bash
cd apps/web
pnpm typecheck
```

### Frontend build (production bundle)

```bash
cd apps/web
pnpm build
```

## Monorepo shortcuts (from repo root)

```bash
pnpm test:web       # frontend tests
pnpm build:web      # frontend build
pnpm typecheck:web  # frontend typecheck
```

---

## What is intentionally NOT implemented yet

Phases 2–9 are implemented on `main` (CRUD, migrations, context-pack
generation, planning UI, Tiptap docs, prompt panel, approval queue, MCP,
external API, read-only Git metadata + Cockpit, Roadmap/Timeline/Agent-Run
analytics, notifications + email reminders). Phase 4b then completed the
Must-have MVP data model (Milestone/Comment/Link/ChecklistItem, migration
`0009`). Still pending:

| Feature | Phase |
|---------|-------|
| Opt-in ChatGPT exposure (go-live) | Phase 7C2b (human-gated) |
| Tauri desktop packaging | Post-V1 / future |
| Auth, billing, cloud deployment | Hosted phase (Phase 10+) |
| CI/CD | Future phase |
