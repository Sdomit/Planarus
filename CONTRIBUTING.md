# Contributing to Planarus

Thanks for your interest. Planarus is a local-first AI project cockpit built
around one idea: **AI agents propose, humans approve.** Contributions that keep
that promise intact are very welcome.

By contributing you agree that your contributions are licensed under the
project's [Apache License 2.0](LICENSE).

## Getting set up

- Full instructions: [docs/dev/setup.md](docs/dev/setup.md).
- One-command local run: `./run-planarus.sh` (macOS/Linux) or `run-planarus.bat` (Windows).
- Backend: `apps/api` — FastAPI + SQLModel + Alembic (Python).
- Frontend: `apps/web` — React + TypeScript + Vite.

## Run the tests

Run both suites before and after your change — a green baseline is required for
any PR:

```bash
# backend, from apps/api
python -m pytest

# frontend, from apps/web
pnpm test
```

Also run the frontend typecheck/build (`pnpm build`) if you touched `apps/web`.

## The invariant you must not break

Planarus's whole value is its trust model. A PR that weakens any of these
will be sent back:

- **External AI surfaces are read/propose-only.** MCP, the HTTP external API,
  and any future agent surface may read data or create *pending proposals* —
  never approve, apply, reject, or invalidate. The internal approval engine is
  the single apply path.
- **The external API stays disabled by default** and binds `127.0.0.1`. Never
  bind `0.0.0.0`; never trust `X-Forwarded-*`.
- **Untrusted tool/endpoint output is redacted and boundary-wrapped** before it
  reaches an agent. Don't add a path that leaks secrets, tokens, or filesystem
  paths.

If your change touches auth, credentials, billing, DB migrations, or `.env*`,
open an issue to discuss it first.

## Pull request flow

1. Fork and branch from `main` with a scoped, descriptive branch name.
2. Keep the change focused — one concern per PR. Match the style of the code
   around you rather than reformatting unrelated lines.
3. Make sure both test suites pass and typecheck/build is clean.
4. In the PR description, say **what** changed, **why**, and **how you
   validated** it.

## Reporting bugs and ideas

- **Security issues:** do not open a public issue — see [SECURITY.md](SECURITY.md).
- **Bugs / features:** open a GitHub issue with repro steps or a clear use case.
- New to the project? Look for issues labelled `good first issue`. If none are
  open yet, say hi in an issue and I'll scope one.

## Where to start reading

- Humans: [docs/plan/00-OVERVIEW.md](docs/plan/00-OVERVIEW.md).
- Agents (Claude Code, Cursor, etc.): [CLAUDE.md](CLAUDE.md) — read it first,
  and don't scan the whole repo.
