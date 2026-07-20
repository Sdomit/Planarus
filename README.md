# Approvo

**AI agents propose. You approve.**

A local-first project cockpit that gives AI coding agents real project context —
and puts a human approval gate in front of every write they attempt.

[![CI](https://github.com/Sdomit/AgentBoard/actions/workflows/ci.yml/badge.svg)](https://github.com/Sdomit/AgentBoard/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Local-first](https://img.shields.io/badge/local--first-no%20cloud%20required-green.svg)](#your-data-stays-yours)

<!-- TODO(screenshots): drop 2-3 current captures in docs/images/ and link them
     here — Cockpit, Approvals, Context Pack. The old marketing shots predate
     the Approvo rename and are no longer accurate. -->

---

## The problem

You use ChatGPT, Claude, Codex, or Cursor to build something real. And every
session, the same two things go wrong:

1. **The agent starts cold.** Your plan lives in a chat transcript it can't see.
   You re-paste context until you run out of patience or tokens.
2. **The agent acts, then you find out.** It edits, commits, and rewrites — and
   your review happens after the fact, if at all.

## What Approvo does

**Gives agents structured context.** Projects, phases, tasks, decisions, risks,
docs, and Git state live in a real database mirrored to Markdown folders you
own. Agents read a *context pack* — a minimal, ordered, token-efficient slice —
instead of your entire repo.

**Puts a gate in front of every agent write.** An agent connected over MCP or
the HTTP API can *read* and can *propose*. It cannot apply. Proposals land in an
approval queue as a preview; a human approves; only then does canonical state
change. This is enforced in one code path, not by convention.

**Runs on your machine.** SQLite, your filesystem, `localhost`. No account, no
cloud, no per-seat pricing. The external API ships **disabled by default** and
bound to loopback; exposing it is an explicit, documented opt-in.

## Quickstart

Docker — no Python, Node, or pnpm toolchain needed:

```bash
git clone https://github.com/Sdomit/AgentBoard.git
cd AgentBoard
docker compose up --build
# → http://localhost:5173
```

Data persists on the host in `./agentboard-data`. Port already taken? Use
`APPROVO_PORT=5174 docker compose up`. Stop with `docker compose down`.

> Creating a project folder in Docker? Put it under `/data` — that's the only
> path that survives `docker compose down`.

**Native, with hot reload:**

```bash
./run-approvo.sh        # macOS / Linux
run-agentboard.bat      # Windows
```

Both check your setup, pick free ports if the defaults are taken, wait until
each server actually answers, then open the UI. First-time toolchain setup is in
[docs/dev/setup.md](docs/dev/setup.md).

## What's in it

Sixteen surfaces over a FastAPI + React stack:

| | |
|---|---|
| **Plan** | Dashboard · Planning (phases, tasks, milestones, decisions, risks, sub-tasks, checklists, custom statuses, board + list views) · Roadmap · Timeline · Calendar |
| **Context** | Docs (rich text) · Context Pack builder · Context Files · Markdown Preview · Canvas (Excalidraw, works offline) |
| **Agents** | Approvals queue · Agent Runs · Reminders · Cockpit (read-only Git + PR view) |
| **Admin** | Team (roles, attribution) · Settings (integrations, webhooks, MCP config, export/import) |

**Connect your agent:** an approval-gated MCP server (STDIO and remote HTTP), a
REST API, and a ChatGPT Actions contract. Configuration is generated for you in
Settings → Integrations.

## Your data stays yours

- Everything is local: SQLite plus Markdown folders you can read, grep, and
  commit yourself.
- **Zero third-party network requests.** Fonts are self-hosted; nothing phones
  home.
- Calendar sync, LAN team mode, outbound webhooks, and the external API all ship
  **off by default** and require explicit configuration.
- Apache-2.0. Fork it, self-host it, no strings.

## How it compares

Notion, ClickUp, and Coda are broad and cloud-first. Linear, Jira, and Height
are product-engineering trackers. Obsidian and Anytype own local knowledge but
aren't agent control planes. None are built around **agent access with an
approval boundary** and **token-efficient context packs** in one local-first
tool. Longer version: [docs/plan/01-product-and-scope.md](docs/plan/01-product-and-scope.md).

## Documentation

- **Using Approvo** → [docs/guide/](docs/guide/) — connect ChatGPT, connect a
  calendar, LAN team mode, team administration.
- **Running it locally** → [docs/dev/setup.md](docs/dev/setup.md)
- **How it's designed** → [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md)
- **Contributing** → [CONTRIBUTING.md](CONTRIBUTING.md)

### For AI agents

This repo is itself managed as an Approvo project, so `context/` is a live
context pack. If you're an agent working here, start at
[CLAUDE.md](CLAUDE.md) → [context/AGENT_RULES.md](context/AGENT_RULES.md) →
[context/NEXT_STEP.md](context/NEXT_STEP.md). Don't scan the whole repo.

## Status

Working local-first app, pre-1.0, built and used daily by its author. Phases
1–17 are merged: planning entities, rich docs, the approval engine, MCP, the
external API, LAN team mode, the repo cockpit, canvas, the 15.x planning line,
team administration, and the integration hub.

Every PR is gated by CI: backend tests, frontend tests, typecheck, production
build, a Postgres migration round-trip, and a Docker Compose build + smoke test.

Not done yet: hosted/SaaS mode is code-complete groundwork but not turned on,
and desktop packaging (Tauri) is not started.

## Contributing & security

Contributions welcome — start with [CONTRIBUTING.md](CONTRIBUTING.md). Please
report security issues privately per [SECURITY.md](SECURITY.md), never as a
public issue.

## License

[Apache License 2.0](LICENSE). Bundled fonts keep their own licenses — see
[NOTICE](NOTICE).
