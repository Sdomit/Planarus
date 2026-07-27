# LAN team mode — setup guide

Share one running Planarus with a small team on the same local network: real
per-person sign-in, one shared database, the same approval boundary. No cloud,
no public exposure, no TLS requirement.

Built by Phase 11 against ratified decisions **D25–D28**:

- **D25** — identity is a local **email+password** account (OAuth needs a public
  redirect URL a LAN box doesn't have). The dev-login provider stays a
  local/test tool; never enable it for a team.
- **D26** — **plain HTTP on the LAN is allowed and is the default.** Your team's
  traffic is UNENCRYPTED on your local network. That is a conscious, documented
  tradeoff — the same one printers, NAS UIs, and most self-hosted tools make.
  If you want TLS, front Planarus with your own reverse proxy; Planarus never
  manages certificates.
- **D27** — presence ("X is editing — read-only") is a polling heartbeat, not
  realtime co-editing. The first active editor of a doc/canvas holds a soft
  lock; everyone else sees a 🔒 banner and a read-only view until they leave.
- **D28** — no hard team-size cap. SQLite (WAL) serializes writers, which is the
  natural "small team" ceiling; if you outgrow it, the SQLite→Postgres ETL
  (`scripts/migrate_db.py`) is the escape hatch.

Everything below is **off by default**. A solo install that skips this page
keeps behaving exactly as before — loopback-only, no accounts.

---

## 1. Turn it on (host machine)

Set the environment for the API process:

```bash
PLANARUS_AUTH_ENABLED=true            # per-person sign-in (required — fail-closed)
PLANARUS_AUTH_PASSWORD_ENABLED=true   # the email+password provider (D25)
PLANARUS_LAN_MODE_ENABLED=true        # the LAN ceiling
PLANARUS_LAN_ALLOWED_HOSTS=192.168.1.50,studio-pc.local
PLANARUS_PROJECTS_ROOT=/srv/planarus/projects   # server-owned project folders (#115, required)
```

Because auth is on, `PLANARUS_PROJECTS_ROOT` is **required** — it is the
server-owned base under which each project's folder lives
(`<base>/<workspace_id>/<project_id>`), so a teammate can never point a project
at another project's files or a server path. The app refuses to start without an
absolute value. Already had projects with hand-picked folders? Bring them under
the base with `python -m app.jobs adopt-roots --apply` (copies then repoints;
the original is left in place).

The launchers fill it in so that a first look at team mode needs no setup at
all: `scripts\run-planarus-team.bat` (or `scripts\run-planarus.bat team`, or
`./scripts/run-planarus.sh team`) defaults it to `%LOCALAPPDATA%\Planarus\projects`
on Windows and `~/.local/share/planarus/projects` elsewhere, and a value already
in the environment wins. For an actual team server, set it yourself — the
default sits under one person's profile, which is the wrong place for everyone
else's files.

`PLANARUS_LAN_ALLOWED_HOSTS` is the exact Host names/IPs teammates will type
into their browser (ports are ignored when matching; IPv6 literals use the
bracket form). Requests for any other Host still get 403 — this is the
DNS-rebinding defense, so keep the list tight.

Two hard rules, both enforced:

- **LAN mode without auth refuses to start** (D25). The local control token is
  not an identity; the app would rather crash loudly than share the DB with a
  network unauthenticated.
- The app itself **never listens beyond loopback** — the socket bind is yours
  (step 2), and the startup log warns about the D26 plain-HTTP tradeoff.

## 2. Serve it to the LAN

**Option A0 — the Windows launcher (steps 1 and 2 in one command):**

```bat
scripts\run-planarus-team.bat lan
scripts\run-planarus-team.bat lan 192.168.1.50
```

`lan` turns on the account gate, LAN mode and the Host allowlist, and binds both
servers past loopback. With no address it uses this machine's own LAN address —
the one teammates would type — and says which it picked; pass one explicitly for
a hostname, a second address, or a comma-separated list. It implies team mode,
because the API refuses to start with LAN mode and no sign-in (D25). It does not
touch the firewall: Windows prompts on first bind, and that prompt is the switch.

**Option A — dev processes (simplest on one workstation):**

```bash
# API: listen on the LAN (your explicit choice)
cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Web: Vite dev server, reachable from the LAN, proxying /api to the local API
cd apps/web && pnpm dev -- --host
```

Teammates browse `http://192.168.1.50:5173`. Add that IP (and only it) to
`PLANARUS_LAN_ALLOWED_HOSTS`… **note:** with the Vite dev proxy, the API sees
Host `localhost` (the proxy runs on the host machine), so strictly only the web
port needs the LAN — but list your LAN IP anyway for direct-API tools.

**Option B — Docker compose:**

`docker-compose.yml` publishes the web UI on loopback only
(`127.0.0.1:5173:80`) by design. For a team, change it to `"5173:80"` and set
the step-1 env vars on the `api` service **first**. The bundled nginx forwards
`/api` with `Host: localhost`, so the host allowlist is satisfied out of the
box; the whole decision reduces to "did you turn auth on before opening the
port". Do not open the port with auth off.

Windows firewall will prompt to allow inbound on the chosen port — that prompt
is your LAN on/off switch at the OS level.

## 3. First accounts and roles

1. **You register first** at the sign-in screen ("Create an account") — email +
   a ≥10-character password. Registration is create-only: an email that already
   has an account can never be claimed again with a new password.
2. Create (or open) your workspace — the creator becomes its **owner**.
3. **Teammates register themselves**, then can see nothing until you grant
   membership. The in-app **Team** view (sidebar, team mode only) does this:
   owners add members by email and set roles there, and server admins can
   create accounts with a one-time temp password instead of waiting for
   self-registration. Full walkthrough + the scripted-provisioning API:
   [team-administration.md](team-administration.md).

   Roles: `owner` (manages members, approves agent proposals), `editor`
   (creates/edits, proposes), `viewer` (read-only).
4. Everyone signs in with email+password; sessions are server-side cookies
   (30-day default). Rotating your password (`POST /api/v1/auth/password/change`)
   signs out every other session for the account.

## 4. What the team gets

- Per-person identity on every action; workspace roles enforced on every
  project-scoped route; approve/apply stays owner-only. External AI clients
  (MCP / external API / GPT) are untouched by LAN mode — still read-and-propose
  only.
- **Presence + soft lock** on docs and canvases (D27): the sidebar of the doc
  shows 🔒 "*Name* is editing — read-only" for everyone but the active editor;
  the lock releases when they leave, switch docs, or go idle ~30s.
- A **Settings → LAN team mode** section: read-only ceiling status plus an
  "Accept teammates from the LAN" switch — unchecking pauses LAN acceptance
  instantly (no restart) without ever affecting loopback; it can never widen
  what the environment forbids.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `RuntimeError: PLANARUS_LAN_MODE_ENABLED requires PLANARUS_AUTH_ENABLED` | The D25 fail-closed check. Turn auth on (step 1). |
| `RuntimeError: PLANARUS_AUTH_ENABLED=true requires an absolute PLANARUS_PROJECTS_ROOT` | The #115 fail-closed check. Set `PLANARUS_PROJECTS_ROOT` to an absolute, writable path (step 1). |
| Teammate gets **403** on every request | Their Host isn't in `PLANARUS_LAN_ALLOWED_HOSTS` (exact name/IP they typed, port ignored), or the Settings LAN switch is unchecked. |
| Sign-in succeeds but immediately forgets the session | You're fronting Planarus with TLS-terminating proxy while LAN mode is off, or accessing over plain HTTP in a mode that requires Secure cookies. Under LAN mode the session cookie deliberately drops the `Secure` flag (D26) so plain HTTP works. |
| "Password sign-in is not enabled on this server" | `PLANARUS_AUTH_PASSWORD_ENABLED` is unset. |
| **429** at sign-in | Per-email throttle: 10 attempts/minute. Wait and retry. |
| Writes feel serialized under load | D28: SQLite's single-writer model. Fine for a small team; the ETL to Postgres is the growth path. |

## Security posture (read once)

Plain HTTP means anyone who can sniff your LAN can read your team's traffic,
including session cookies (D26 — accepted tradeoff, loud warning at startup and
in Settings). Passwords are stored only as Argon2id hashes; session tokens only
as SHA-256 hashes; login failures are generic and throttled. The exposure
boundary remains: your OS firewall + the Host allowlist + auth. If any of that
is unacceptable for your network, front Planarus with your own TLS reverse proxy
or don't open the port.
