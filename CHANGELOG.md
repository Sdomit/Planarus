# Changelog

All notable user-facing release changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project is pre-1.0
and does not yet claim [Semantic Versioning](https://semver.org/) guarantees.

## [Unreleased]

No tagged release has been published yet. Everything below is what a reader
gets by cloning `main` today, recorded so the first tagged release has a
starting point rather than an empty file.

### Added

- **Local-first planner, complete with no agent connected.** Projects, phases,
  stages, milestones, tasks and sub-tasks, decisions, risks, checklists,
  comments, links, todos, documents and canvases, over board, roadmap, timeline
  and calendar views. SQLite in WAL mode, on your own project folders.
- **Notion-style document editor.** A `/` menu inserts headings, quotes,
  dividers, lists, toggles, callouts and tables. Sub-pages live inline: a page
  block opens a child document, "convert to page" turns a line of text into one,
  and removing the block detaches the child rather than deleting it. The document
  list is an indented, collapsible tree with drag-to-reparent, and the editor
  shows a breadcrumb up the parent chain.
- **`@` mentions and backlinks.** Type `@` in a document to reference a task,
  decision, risk, milestone, phase or another document. Each referenced item's
  detail view lists the documents that mention it. References are derived from
  the document body on save rather than maintained by hand, so they cannot drift
  from what the document actually says, and they survive project duplication and
  export. Mentions and sub-pages both export as ordinary Markdown links, so the
  exported files stay readable in any viewer.
- **The approval boundary.** Every agent-originated write becomes a pending
  approval request carrying a diff. Approving, applying, rejecting and
  invalidating require a local control token, so no external agent can approve
  its own proposal.
- **MCP server.** Planarus serves the Model Context Protocol over STDIO for
  local clients (Claude Code, Claude Desktop, Cursor, Windsurf, VS Code) and over
  opt-in HTTP for remote ones. Tools are `read_*` and `propose_*` only. Settings
  → Integrations generates the client configuration to paste.
- **External REST surface for GPT Actions.** Disabled by default behind
  `PLANARUS_EXTERNAL_API_ENABLED`. Bearer keys (`agbk_…`, Argon2id-hashed) carry
  per-project read/propose scopes, expiry and rate limits; the committed OpenAPI
  documents in [`docs/api/`](docs/api/) are verified byte-for-byte against the
  builder in CI. Offset pagination on the collection routes.
- **Agent run log.** A manual record of which assistant did what, with success
  rate and duration analytics. Never written by an agent.
- **LAN team mode.** Opt-in email/password identity, owner/editor/viewer roles,
  a workspace membership model, presence heartbeats, a Host allowlist against
  DNS rebinding, and a configurable CORS origin list — one shared instance for a
  small team on a local network, no cloud and no TLS requirement. See
  [`docs/guide/lan-team-mode.md`](docs/guide/lan-team-mode.md).
- **Team administration.** In-app Team view plus a scripted provisioning API.
- **Browser extension (Chrome/Edge, MV3).** Select text on any page and file it
  as a task, phase, decision, risk or note; optional toolbar badge showing the
  pending-approval count. The capture half holds no credential and makes no
  network request of its own.
- **Optional integrations, all off by default.** Google and Microsoft calendar
  sync, webhooks, scheduled reminders, and verified database backups.
- **Docker Compose quickstart.** `docker compose up --build` with no Python,
  Node or pnpm on the host; loopback-only port publishing by default.
- **Windows without Docker.** `scripts\run-planarus.bat` offers to install Node
  and Python 3.11 through winget when they are missing, builds the virtual
  environment, installs dependencies, migrates, moves off 5173/8000 if they are
  busy, waits for both services and opens the browser. Alongside it:
  `stop-planarus.bat`, `planarus-tray.bat` for a notification-area icon that
  starts, stops and opens the app, and `create-shortcuts.bat` for Desktop
  shortcuts.

### Fixed

Nothing here has been released, so these are not upgrade notes. They are
recorded because each one made the Windows path unusable and none were caught
by a green build:

- `run-planarus.bat` aborted before its first command on every invocation. A
  `%~f` inside a `REM` comment — cmd substitutes parameter references in
  comments too — was reported as an invalid path operator.
- It could never create `apps/api/.venv`. `%BOOTSTRAP_PY%` was read inside a
  parenthesised block, so it was substituted at parse time, before the call that
  sets it had run, and the line executed as `-m venv ...`. Every fresh checkout
  failed at the first bootstrap step.
- `create-shortcuts.bat` wrote junk files instead of printing. An unescaped `>`
  in `echo ... -> ...` is a redirect.
- The tray hung before it could show itself. It read ports by shelling out to
  `tasklist`, which a hidden console-less PowerShell cannot depend on; the call
  never returned, so the icon was never shown and the menu never opened. Ports
  now come from a file the launcher writes, confirmed by a socket probe.
- Tray menu actions failed silently, because WinForms discards exceptions thrown
  in a click handler. They now log to `%LOCALAPPDATA%\Planarus\tray.log` and
  raise a balloon on failure.

CI gained a `windows-latest` job that runs these scripts, including a cold
bootstrap on a checkout with no virtual environment. Nothing had executed them
before, which is why all of the above shipped.

### Changed

- **Node 24.** CI, `.nvmrc` and the web Dockerfile move off Node 20, which
  reached end of life in April 2026; `engines` now requires `>=22`.
- **jsdom held at 29.** jsdom 30's rewritten CSS engine throws from
  `getComputedStyle`, which testing-library calls on every visibility check.
  Dependabot is told to hold the major until a 30.x patch lands.

### Known limitations

- **Single API process.** Rate limiting, the local control token, the LAN-mode
  switch and presence tracking are all process-local, so the API does not run
  behind more than one replica.
- **One hostname for web and API.** The web client calls a relative `/api/v1`
  and is served through a proxy that fronts both; there is no build-time API URL
  to point at a different host.
- **Hosted deployment is groundwork, not a supported path.** The stack under
  [`deploy/`](deploy/) has not been machine-validated end to end.
- **No desktop installer.** Tauri packaging is planned and not started. The
  Windows scripts above need the repository on disk first, so a reader still
  needs Git or a ZIP download before anything can be double-clicked.
- **Chrome and Edge only** for the extension; Firefox and Safari need their own
  pass.
- **Never installed from a clean machine.** CI proves the Docker stack builds
  and answers, and now that the Windows launcher bootstraps from a checkout with
  no virtual environment. Neither is the same as someone cloning this repository
  on a machine that has never run it.

### Release metadata

All four version manifests now agree on `0.2.0` — `Settings.app_version`,
`apps/api/pyproject.toml`, the root `package.json` and `apps/web/package.json` —
and `test_version_single_source` fails if they drift apart again. `0.2.0` is a
development version, not a chosen release version.

## Release policy

Planarus remains pre-1.0 until the owner selects a release version and confirms
the launch, support, and distribution model. Published version numbers are
never reused or silently replaced.
