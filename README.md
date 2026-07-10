# AgentBoard

> A **local-first AI project cockpit**. One place that converts long AI
> conversations, implementation plans, Git context, decisions, risks, and
> execution history into **structured project memory** that humans *and* agents
> can both use.

AgentBoard is not "another project manager." It is an **AI execution control
plane**: human planning (projects → phases → stages → tasks), an agent context
layer (Markdown context packs, allowed/forbidden paths, prompts, approval
gates), and an execution telemetry layer (agent runs, Git state, imports, audit
log) — all stored locally in real folders you own.

---

## Status

**Working local-first app.** `apps/api` (FastAPI + SQLModel + Alembic) and
`apps/web` (React + TS + Vite) ship seven surfaces: Dashboard, Planning, Docs,
Context Pack, Context Files, Approvals, Clients. Test baseline on `main`:
**512 pytest passed / 1 skipped, 54 vitest**. The external API exists but is
**disabled by default** (loopback-bound; enabling it is an explicit user opt-in).
One-command local run: `run-agentboard.bat`.

| Artifact | Location |
|---|---|
| Source research | [deep-research-report.md](deep-research-report.md) |
| Architecture & MVP plan | [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md) |
| Living context pack (read first as an agent) | [context/](context/) |
| Agent routing instructions | [CLAUDE.md](CLAUDE.md) |
| Developer setup | [docs/dev/setup.md](docs/dev/setup.md) |

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

Merge the 2026-07-10 review-fix branches, then either execute the Phase 7C2b
opt-in ChatGPT exposure (human-gated — see
[docs/dev/phase-7c2b-go-live-runbook.md](docs/dev/phase-7c2b-go-live-runbook.md))
or merge Phase 8 (read-only Git metadata). Live objective:
[context/NEXT_STEP.md](context/NEXT_STEP.md).

## License

Undecided; **Apache-2.0** is the recommended default for a future public/commercial
product. See the licensing note in
[docs/plan/10-risks-and-decisions.md](docs/plan/10-risks-and-decisions.md).
