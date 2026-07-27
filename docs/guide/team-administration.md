# Team administration — roles, accounts, and provisioning

Once [LAN team mode](lan-team-mode.md) (or a hosted deployment) is on, Planarus
has real per-person accounts. This guide covers the layer on top: **who can do
what**, the in-app **Team** view for managing people, and the **scripted API**
for provisioning users from IT tooling or another system.

Built by Phase 16 against ratified decisions **D29–D35**
([../plan/14-team-admin.md](../plan/14-team-admin.md),
[../../context/DECISIONS.md](../../context/DECISIONS.md)). Everything here is
dormant in local single-user mode — a solo install never sees a Team tab, an
account, or an admin.

> **Prerequisite:** sign-in must be enabled. See
> [lan-team-mode.md §1](lan-team-mode.md) for the environment
> (`PLANARUS_AUTH_ENABLED=true`, `PLANARUS_AUTH_PASSWORD_ENABLED=true`, and
> the LAN ceiling if you're serving a network). With auth off, every route and
> screen below returns 404 / is hidden.

## 0. The first ten minutes

```
scripts\run-planarus.bat team          # Windows
./scripts/run-planarus.sh team         # macOS / Linux
```

That flag is the whole environment — it sets `PLANARUS_AUTH_ENABLED` and
`PLANARUS_AUTH_PASSWORD_ENABLED` for the two servers it starts and nothing else
on your machine. A plain run stays the single-user local tool with no sign-in.

1. **Claim the server.** An install with no accounts opens on **Set up
   Planarus** instead of a sign-in form. The account you create there becomes
   the server admin (D29) — there is no separate "make me admin" step, and it
   only happens once.
2. **Add a teammate.** Account chip (bottom-left) → **Team** → create a user,
   pick their workspace and role. You get a one-time temporary password to hand
   over; they must replace it at first sign-in.
3. **Add a read-only guest.** Same form, role `viewer`. They can see everything
   in that workspace and change nothing — enforced server-side, not just hidden
   in the UI. This is the supported "guest access": an invite, not a mode.
4. **Check it worked.** Sign out, sign in as the viewer, try to edit something.
   It should refuse.

### If nobody can sign in

There is no self-service password reset (D54 — a reset email has nowhere to go
until outbound email ships). Two routes back in:

- **Another admin** resets it from Team.
- **No admin can sign in?** On the machine hosting Planarus:

```
python -m app.jobs admin --list                        # who owns this server
python -m app.jobs admin --reset-password you@example  # prints a temp password
python -m app.jobs admin --grant you@example           # promote to admin
```

Run these from `apps/api` with the venv active. `--reset-password` prints the
password once, forces a change at sign-in, and signs that account out
everywhere. It is a CLI and never an HTTP route (D53): anyone who can run it
already has your database file, so it adds convenience rather than a new way in.

## 1. Two kinds of authority

Planarus separates **project authority** from **account authority** — different
scopes, granted independently.

| | Governs | Granted by |
|---|---|---|
| **Workspace role** — `owner` / `editor` / `viewer` | project *content* + the approve/apply gate, per workspace (D19/D22) | a workspace **owner** |
| **Server admin** (`is_admin`) | *accounts* + server management (create/reset/deactivate users, server switches, API keys) | another **server admin** |

**Admin is not data access.** A server admin manages accounts but sees a
project's data only if they're also a member of its workspace. This keeps
audits honest and least-surprising: the person who resets passwords isn't
silently reading every project.

The **first account** to register on a fresh server becomes its admin
(bootstrap). After that, admins grant admin to others.

### Who can do what

| Action | Viewer | Editor | Owner | Server admin |
|---|:---:|:---:|:---:|:---:|
| Read project data (via membership) | ✓ | ✓ | ✓ | only via membership |
| Create/edit entities, propose changes | – | ✓ | ✓ | only via membership |
| Approve / apply agent proposals (D22) | – | – | ✓ | only if also owner |
| Manage a workspace's members & roles | – | – | ✓ | – |
| See the account roster / who's online | – | – | – | ✓ |
| Create accounts, reset passwords, deactivate | – | – | – | ✓ |
| Grant / revoke server admin | – | – | – | ✓ |
| Flip server switches, mint external API keys | – | – | – | ✓ |

External AI clients (MCP, the external API, a GPT Action) appear on **no** row:
they may only read or create pending proposals — never approve, apply, or
administer. No admin route is exposed on `/api/external`, and an `agbk_` API key
can never manage accounts (D31).

## 2. The Team view (in-app)

Sign in, then open **Team** in the sidebar (visible only in team mode). Three
sections, shown according to your authority:

- **Your account** — avatar, name, email, and **Change password** (rotating it
  signs out every *other* session for your account).
- **Accounts** *(server admins only)* — the full roster: avatar, admin/
  deactivated badges, and last-seen with an "online now" dot. Per person:
  - **Add user** → creates the account and shows a **one-time temporary
    password**. Copy it and hand it over; it is shown once and stored only as a
    hash. The teammate must replace it at first sign-in.
  - **Reset password** → new one-time temp password; all their sessions are
    signed out.
  - **Deactivate / Reactivate** → a deactivated account is signed out
    everywhere and cannot sign in until reactivated. Accounts are never
    hard-deleted (D34), so past attribution keeps resolving.
  - **Make / Remove admin**.
  - Guardrail: the **last active admin** can't be deactivated or demoted.
- **Workspace members** — for each workspace you belong to. **Owners** add
  members by email, change roles inline, and remove people; everyone else sees
  a read-only roster. Guardrail: the **last owner** of a workspace can't be
  removed or demoted.

## 3. Onboarding a teammate

Two paths — pick per how open your environment is.

**A · Self-registration (default).** The teammate opens the sign-in screen,
chooses "Create an account", and registers with email + a ≥10-char password.
Then a workspace **owner** adds them to a workspace (Team → Workspace members,
or the API in §4). Until then a fresh account can see nothing.

**B · Admin-created (controlled).** A server admin uses **Team → Accounts → Add
user**, hands over the one-time temp password, and the teammate is forced to
change it on first sign-in. Then an owner grants workspace membership.

**Closing the door.** After onboarding, turn off open self-registration:
**Settings → LAN team mode → "Accept self-registration on the sign-in screen"**
(the `registration_open` switch). With it off, the register form returns the
same generic "not found" as a disabled server — admin-created accounts (path B)
become the only way in. Existing accounts and admin creation are unaffected.

## 4. Scripted provisioning (network admins & integrations)

There is **no separate admin token or API key** — scripted provisioning uses
the same session an admin gets in the browser. A service account signs in, then
calls the `/api/v1/admin/*` routes with its **session cookie** plus the
**local control token** (a CSRF guard on every state change, fetched from
`/local-session`). Read-only calls (the roster) need only the cookie.

Set up a dedicated admin **service account** (create it in the Team view, sign
in once to clear its temp password) rather than scripting a real person's login.

### The admin routes

All under `/api/v1`. Mutations require `X-Planarus-Local-Token`; all require an
admin session cookie.

| Method + path | Effect |
|---|---|
| `GET /admin/users` | The roster (id, email, name, is_admin, is_active, last_seen, memberships) |
| `POST /admin/users` | Create an account → returns a one-time `temp_password` |
| `POST /admin/users/{id}/reset-password` | New one-time `temp_password`; revokes their sessions |
| `POST /admin/users/{id}/deactivate` · `/reactivate` | Flip `is_active` |
| `PATCH /admin/users/{id}` | `{"is_admin": true|false}` |
| `POST /workspaces/{ws}/members` | Add a member `{"email","role"}` (they must already have an account) |
| `PATCH /workspaces/{ws}/members/{user_id}` | Change role `{"role"}` |
| `DELETE /workspaces/{ws}/members/{user_id}` | Remove a member |

Run from the host machine (loopback is always allowed) or from a Host in
`PLANARUS_LAN_ALLOWED_HOSTS`.

### Bash / curl

```bash
BASE=http://localhost:8000/api/v1

# 1. sign in as the admin service account; keep the session cookie
curl -s -c cookies.txt -X POST "$BASE/auth/password/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"provisioner@studio.lan","password":"<password>"}'

# 2. fetch the control token (CSRF guard for mutations)
TOKEN=$(curl -s -b cookies.txt "$BASE/local-session" | jq -r .token)

# 3. create an account — capture the one-time temp password to hand over
curl -s -b cookies.txt -X POST "$BASE/admin/users" \
  -H "X-Planarus-Local-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"newhire@studio.lan","display_name":"New Hire"}'

# 4. add them to a workspace as an editor
curl -s -b cookies.txt -X POST "$BASE/workspaces/<ws_id>/members" \
  -H "X-Planarus-Local-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"newhire@studio.lan","role":"editor"}'
```

### PowerShell

```powershell
$base = 'http://localhost:8000/api/v1'
$login = @{ email = 'provisioner@studio.lan'; password = '<password>' } | ConvertTo-Json
Invoke-RestMethod "$base/auth/password/login" -Method Post -Body $login `
  -ContentType 'application/json' -SessionVariable s | Out-Null
$token = (Invoke-RestMethod "$base/local-session" -WebSession $s).token
$hdr = @{ 'X-Planarus-Local-Token' = $token }

$body = @{ email = 'newhire@studio.lan'; display_name = 'New Hire' } | ConvertTo-Json
$acct = Invoke-RestMethod "$base/admin/users" -Method Post -WebSession $s `
  -Headers $hdr -Body $body -ContentType 'application/json'
$acct.temp_password   # hand this to the new hire (shown once)
```

This maps 1:1 onto an IdP's user-lifecycle verbs (create / deactivate /
reactivate), so a SCIM or directory-sync adapter is a thin wrapper over these
four calls — build it when an org with an IdP actually asks.

## 5. Faces — who did what

With accounts in place, Planarus attributes actions to people (D32/D33):

- **Tasks** carry an **assignee** — set it in the task detail, scan it as a chip
  on each row, and use the **"Assigned to me"** filter.
- **Comments** show their **author**; **docs** show **who last edited** them.
- The **project timeline** and **approval history** name the person who made
  each change and who approved each proposal (instead of a generic "human").

None of this is retroactive — rows created before an account existed stay
unattributed — and all of it is empty in local single-user mode.

## 6. Security posture (read once)

- **Temp passwords** are shown exactly once and stored only as Argon2id hashes;
  reset and deactivate revoke every session for the account.
- **No hard delete** of accounts (D34) — deactivation is the terminal state, so
  the audit trail and "decided by" keep resolving.
- The **last active admin** and the **last workspace owner** are protected from
  self-lockout.
- With auth on, flipping server switches and minting external API keys require
  a **server admin** (D35) — the local control token alone is a CSRF guard the
  served web app hands to every browser, not an identity.
- The LAN transport caveat still applies: plain HTTP on a LAN is unencrypted
  (D26). Temp passwords cross that wire in the clear unless you front Planarus
  with TLS — see [lan-team-mode.md → Security posture](lan-team-mode.md).
