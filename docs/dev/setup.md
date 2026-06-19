---
kind: dev_guide
updated_at: 2026-06-19
phase: 1-foundation
---

# Developer setup — Phase 1

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

# Install runtime + dev dependencies
pip install -e ".[dev]"

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

Expected output: 3 tests pass (health, info, openapi schema).

### Frontend

```bash
cd apps/web
pnpm test
```

Expected output: 1 test suite, 1 test passes (smoke render).

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

## What is intentionally NOT implemented in Phase 1

| Feature | Phase |
|---------|-------|
| Project / task CRUD | Phase 2 |
| SQLite schema + Alembic migrations | Phase 2 |
| Markdown context-pack generation | Phase 3 |
| Planning hierarchy UI (tree, kanban) | Phase 4 |
| Rich Tiptap editor | Phase 5 |
| AI context / prompt panel | Phase 6 |
| Approval queue + MCP/REST external surfaces | Phase 7 |
| Read-only Git metadata | Phase 8 |
| Tauri desktop packaging | Phase 9 or later |
| Auth, billing, cloud deployment | Hosted phase (Phase 10+) |
| Email, CI/CD, migrations | Respective future phases |
