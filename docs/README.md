# Planarus documentation

## Using Planarus

Start here if you're running it, not building it.

| Guide | What it covers |
|---|---|
| [dev/setup.md](dev/setup.md) | Running locally with hot reload (Docker needs none of it — see the [README quickstart](../README.md#quickstart)) |
| [guide/connect-planarus-to-chatgpt.md](guide/connect-planarus-to-chatgpt.md) | Exposing the read-only API to a private GPT — human-gated, read this fully first |
| [guide/connect-your-calendar.md](guide/connect-your-calendar.md) | Optional Google / Microsoft calendar sync (off by default) |
| [guide/lan-team-mode.md](guide/lan-team-mode.md) | Sharing one instance across a LAN (off by default; turn auth on first) |
| [guide/team-administration.md](guide/team-administration.md) | Accounts, roles, and attribution |
| [guide/notifications-and-backup.md](guide/notifications-and-backup.md) | Scheduled reminders and verified DB backups (OS scheduler, off by default) |
| [guide/hosted-go-live.md](guide/hosted-go-live.md) | Hosted deployment groundwork — not turned on |

**Supported browsers:** current Chrome/Edge, Firefox, and Safari 16.4+. Planarus
is a desktop-first cockpit; it is usable on a tablet and readable on a phone,
but the board, canvas, and timeline surfaces assume a wide viewport.

## Understanding the design

| Doc | What it covers |
|---|---|
| [plan/00-OVERVIEW.md](plan/00-OVERVIEW.md) | Index of the architecture and product plan |
| [plan/01-product-and-scope.md](plan/01-product-and-scope.md) | What Planarus is and isn't, and how it compares |
| [plan/02-architecture.md](plan/02-architecture.md) | Stack rationale |
| [plan/03-data-model.md](plan/03-data-model.md) | Entities and relationships |
| [plan/06-governance-mcp-api-chatgpt.md](plan/06-governance-mcp-api-chatgpt.md) | The approval boundary and agent access |
| [plan/10-risks-and-decisions.md](plan/10-risks-and-decisions.md) | Decision log |

## Build history

`dev/phase-*.md` is a per-phase record of how each slice was built and why —
useful archaeology when you're wondering why something is the way it is, and
safe to ignore otherwise. `api/` holds the generated OpenAPI contracts.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md). If you're an AI agent working in this
repo, start at [CLAUDE.md](../CLAUDE.md) instead — this repo is itself managed
as an Planarus project and `context/` is a live context pack.
