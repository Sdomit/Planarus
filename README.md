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

**Phase: architecture lock (pre-code).** No application code exists yet. This
repository currently holds the research, the locked architecture plan, and
AgentBoard's own context pack.

| Artifact | Location |
|---|---|
| Source research | [deep-research-report.md](deep-research-report.md) |
| Architecture & MVP plan (start here) | [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md) |
| Living context pack (read first as an agent) | [context/](context/) |
| Agent routing instructions | [CLAUDE.md](CLAUDE.md) |

## The locked stack (one line)

React + Tiptap UI → packaged with **Tauri** for desktop and served as a normal
web app → talking to a **FastAPI** backend (run as a Tauri sidecar on desktop)
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

Phase 0 is the documentation-only architecture acceptance gate described in
[docs/plan/08-implementation-phases.md](docs/plan/08-implementation-phases.md).
After a second review accepts the plan, the first code branch is
`feat/phase-1-foundation`.

## License

Undecided; **Apache-2.0** is the recommended default for a future public/commercial
product. See the licensing note in
[docs/plan/10-risks-and-decisions.md](docs/plan/10-risks-and-decisions.md).
