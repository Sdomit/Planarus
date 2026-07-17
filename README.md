# Approvo

> A **local-first AI project cockpit**. One place that converts long AI
> conversations, implementation plans, Git context, decisions, risks, and
> execution history into **structured project memory** that humans *and* agents
> can both use.

Approvo is not "another project manager." It is an **AI execution control
plane**: human planning (projects → phases → stages → tasks), an agent context
layer (Markdown context packs, allowed/forbidden paths, prompts, approval
gates), and an execution telemetry layer (agent runs, Git state, imports, audit
log) — all stored locally in real folders you own.

---

## Status

**Working local-first app.** `apps/api` (FastAPI + SQLModel + Alembic) and
`apps/web` (React + TS + Vite) ship fifteen surfaces: Dashboard, Cockpit,
Planning (phases/tasks/milestones/decisions/risks/comments/links — with board
views, custom statuses, sub-tasks, and task checklists), Roadmap, Timeline,
Calendar (with optional external Google/Microsoft sync), Docs, Context Pack,
Context Files, Markdown Preview, Approvals, Clients, Agent Runs, Reminders, and
Settings — plus a project-scoped sidebar todo list. Test baseline:
**815 pytest passed / 3 skipped, 131 vitest**. The external API exists but is
**disabled by default** (loopback-bound; enabling it is an explicit user opt-in).
One-command local run: `run-agentboard.bat`.

| Artifact | Location |
|---|---|
| Source research | [deep-research-report.md](deep-research-report.md) |
| Architecture & MVP plan | [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md) |
| Living context pack (read first as an agent) | [context/](context/) |
| Agent routing instructions | [CLAUDE.md](CLAUDE.md) |
| Developer setup | [docs/dev/setup.md](docs/dev/setup.md) |

## Quickstart (Docker)

The fastest way to try Approvo — no Python, Node, or pnpm toolchain required:

```bash
docker compose up --build
# then open http://localhost:5173
```

This runs the web UI (nginx) and the API as containers on a private network; the
external (ChatGPT) API stays **disabled**. Your data — the SQLite DB and any
project folders you create under `/data` — persists on the host in
`./agentboard-data`. Stop with `docker compose down`.

Prefer a native setup with hot reload? See
[docs/dev/setup.md](docs/dev/setup.md) (or `run-agentboard.bat` on Windows).

## The locked stack (one line)

React + Tiptap UI → served as a normal web app today (**Tauri** desktop
packaging deferred to Phase 9+) → talking to a **FastAPI** backend
→ **SQLite** locally (SQLAlchemy/SQLModel + Alembic, Postgres-ready) → every
project mirrored to a **real folder of Markdown context files** → a narrow,
approval-gated **MCP** server and REST API for agents.

Full rationale: [docs/plan/02-architecture.md](docs/plan/02-architecture.md).

## What makes it different

Notion/ClickUp/Coda are broad and cloud-first. Linear/Jira/Height are
product-engineering trackers. Obsidian/Anytype/Capacities own local knowledge
but are not agent control planes. **None** are purpose-built around
ChatGPT import/update *with an approval flow*, MCP-native *but permission-safe*
agent access, Markdown *context packs*, and token-efficient agent orchestration
— in one local-first product. See
[docs/plan/01-product-and-scope.md](docs/plan/01-product-and-scope.md).

## For humans vs. for agents

- **Humans** start at [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md).
- **Agents** start at [CLAUDE.md](CLAUDE.md) → [context/AGENT_RULES.md](context/AGENT_RULES.md)
  → [context/NEXT_STEP.md](context/NEXT_STEP.md). Do not scan the whole repo.

## Next implementation step

Phases 1–10, 13 (local canvas), and the 15.x line (planning boards, custom
statuses, sub-tasks, calendar + optional external sync) are built and merged.
The current objective is **OSS launch prep**; the next optional milestones are
the human-gated Phase 7C2b ChatGPT exposure
([docs/dev/phase-7c2b-go-live-runbook.md](docs/dev/phase-7c2b-go-live-runbook.md))
and hosted go-live (code-complete, user setup only). Live objective:
[context/NEXT_STEP.md](context/NEXT_STEP.md).

## Contributing & security

Contributions are welcome — start with [CONTRIBUTING.md](CONTRIBUTING.md). Please
report security issues privately per [SECURITY.md](SECURITY.md), not via public
issues.

## License

[Apache License 2.0](LICENSE). Rationale in
[docs/plan/10-risks-and-decisions.md](docs/plan/10-risks-and-decisions.md).
