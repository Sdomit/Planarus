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

The architecture is described where it is enforced rather than in a parallel
set of documents: the entity model in `apps/api/app/models/`, the approval
boundary in `apps/api/app/policy/` and `apps/api/app/services/approval_service.py`,
and the external contract in [api/](api/), which holds the generated OpenAPI
documents. The test suite under `apps/api/tests/` is the executable spec.

Source comments occasionally cite `docs/plan/*.md` — the working design notes.
Those are maintainer-local and not published; see "What is not in this repo"
below.

## API contracts

`api/` holds the generated OpenAPI documents for the external surface — the
read-only contract and the read-plus-propose contract used by the ChatGPT
actions integration.

## What is not in this repo

Three kinds of working material are deliberately kept off the published tree:
the agent operating pack (`CLAUDE.md`, `AGENTS.md`, `context/`), the design
notes (`docs/plan/`), and the per-phase build record (`docs/dev/phase-*.md`).

They describe how Planarus is developed, not what it ships, and several of them
are point-in-time snapshots that would be stale on arrival. Excluding them keeps
the published repo to the things a reader can actually act on: the code, the
tests, the deploy artifacts, and the guides above.

## Contributing

See [CONTRIBUTING.md](../.github/CONTRIBUTING.md).
