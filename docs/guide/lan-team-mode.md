# LAN team mode — setup guide

Share one running Approvo with a small team on the same local network: real
per-person sign-in, one shared database, the same approval boundary. No cloud,
no public exposure, no TLS requirement.

Built by Phase 11 against ratified decisions **D25–D28**
([../plan/13-lan-team-mode.md](../plan/13-lan-team-mode.md),
[../../context/DECISIONS.md](../../context/DECISIONS.md)):

- **D25** — identity is a local **email+password** account (OAuth needs a public
  redirect URL a LAN box doesn't have). The dev-login provider stays a
  local/test tool; never enable it for a team.
- **D26** — **plain HTTP on the LAN is allowed and is the default.** Your team's
  traffic is UNENCRYPTED on your local network. That is a conscious, documented
  tradeoff — the same one printers, NAS UIs, and most self-hosted tools make.
  If you want TLS, front Approvo with your own reverse proxy; Approvo never
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
AGENTBOARD_AUTH_ENABLED=true            # per-person sign-in (required — fail-closed)
AGENTBOARD_AUTH_PASSWORD_ENABLED=true   # the email+password provider (D25)
AGENTBOARD_LAN_MODE_ENABLED=true        # the LAN ceiling
AGENTBOARD_LAN_ALLOWED_HOSTS=192.168.1.50,studio-pc.local
```

`AGENTBOARD_LAN_ALLOWED_HOSTS` is the exact Host names/IPs teammates will type
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

**Option A — dev processes (simplest on one workstation):**

```bash
# API: listen on the LAN (your explicit choice)
cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Web: Vite dev server, reachable from the LAN, proxying /api to the local API
cd apps/web && pnpm dev -- --host
```

Teammates browse `http://192.168.1.50:5173`. Add that IP (and only it) to
`AGENTBOARD_LAN_ALLOWED_HOSTS`… **note:** with the Vite dev proxy, the API sees
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
   membership. There is no members UI yet, so the owner grants roles via the
   API (from the host machine or any signed-in owner session):

   ```bash
   curl -X POST http://localhost:8000/api/v1/workspaces/<ws_id>/members \
     -H "Content-Type: application/json" -b "approvo_session=<your cookie>" \
     -d '{"email": "teammate@example.com", "role": "editor"}'
   ```

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
| `RuntimeError: AGENTBOARD_LAN_MODE_ENABLED requires AGENTBOARD_AUTH_ENABLED` | The D25 fail-closed check. Turn auth on (step 1). |
| Teammate gets **403** on every request | Their Host isn't in `AGENTBOARD_LAN_ALLOWED_HOSTS` (exact name/IP they typed, port ignored), or the Settings LAN switch is unchecked. |
| Sign-in succeeds but immediately forgets the session | You're fronting Approvo with TLS-terminating proxy while LAN mode is off, or accessing over plain HTTP in a mode that requires Secure cookies. Under LAN mode the session cookie deliberately drops the `Secure` flag (D26) so plain HTTP works. |
| "Password sign-in is not enabled on this server" | `AGENTBOARD_AUTH_PASSWORD_ENABLED` is unset. |
| **429** at sign-in | Per-email throttle: 10 attempts/minute. Wait and retry. |
| Writes feel serialized under load | D28: SQLite's single-writer model. Fine for a small team; the ETL to Postgres is the growth path. |

## Security posture (read once)

Plain HTTP means anyone who can sniff your LAN can read your team's traffic,
including session cookies (D26 — accepted tradeoff, loud warning at startup and
in Settings). Passwords are stored only as Argon2id hashes; session tokens only
as SHA-256 hashes; login failures are generic and throttled. The exposure
boundary remains: your OS firewall + the Host allowlist + auth. If any of that
is unacceptable for your network, front Approvo with your own TLS reverse proxy
or don't open the port.
