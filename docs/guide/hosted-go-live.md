# Going live: hosted Planarus (OAuth + S3)

Everything hosted is **off by default** and config-driven, so going live is
providing infrastructure and secrets, not writing code. Work top-to-bottom; the
last step (`doctor`) verifies the whole thing before you deploy.

**Read [§0 Supported topology](#0-supported-topology-read-this-first) first.**
Pre-1.0 Planarus is supported on **exactly one API process and one replica**.
That is the only runtime it is tested against, and the app refuses to start in
the multi-worker configurations it can detect.

All settings are `PLANARUS_*` env vars; `apps/api/deploy/hosted.env.example` is a
fill-in-the-blanks template.

## 0. Supported topology (read this first)

| | Supported pre-1.0 |
|---|---|
| API processes | **1** — no `--workers N`, no `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1, no gunicorn |
| Replicas / instances | **1** — no autoscaling, no multi-region, no warm standby serving traffic |
| Deploys | **stop-then-start.** No rolling deploy that runs the old and new instance concurrently |
| Database | managed Postgres is fine — it is the only shared store |
| Local-disk features | require a single server-owned mounted volume attached to that one instance |

**Why.** Several security and coordination controls are deliberately
process-local at this stage, so a second process is not a second copy — it is a
divergent one:

| Process-local state | Where | What a second process breaks |
|---|---|---|
| Login rate-limit buckets, external-API concurrency counters | `core/rate_limit.py` (module-level `limiter`) | N workers = N× the limit an attacker actually gets |
| Local control token | `core/security.py` `_LOCAL_CONTROL_TOKEN` | the token minted by one process is rejected by the other |
| LAN acceptance switch mirror | `services/settings_service.py` `_lan_switch_cache` | turning LAN mode **off** only reaches the worker that served the write |
| Document presence / soft-locks | in-process by design | two users can hold the "same" lock |
| Local filesystem storage + managed project roots | — | assume one node owns the disk |
| S3 `append_line` | `storage/s3.py` | read-modify-write with no distributed lock — concurrent appends silently lose data |

**Not on that list: OAuth.** Sign-in state used to be an HMAC blob signed with a
per-process key — invisible to a second worker and lost on restart. #113
replaced it with a one-time server-side `oauthtransaction` row shared by the
login and calendar flows, so OAuth already survives restarts and would survive
multiple workers. It is the one piece of this that is already shared.

**What is enforced vs. what you must guarantee.** The app fails closed on
`WEB_CONCURRENCY` or `UVICORN_WORKERS` greater than 1 (or unparseable, e.g.
`auto`) — it raises at startup rather than serving. It **cannot** see your
replica count, autoscaling policy, or rolling-deploy overlap, and it cannot see
a `--workers 4` typed directly into a start command. Those are yours to get
right; `doctor` prints them as explicit obligations rather than assuming them.

**Restart behaviour.** A restart re-mints the local control token, empties the
rate-limit buckets, and clears presence/soft-lock state. Nothing is corrupted and
signed-in users stay signed in. Prefer restarting when idle; a restart under load
briefly resets the rate-limit window.

Need real multi-worker/multi-node scale-out? That is issue
[#120](https://github.com/Sdomit/Planarus/issues/120) Option B — shared OAuth
transaction state, centralised rate limits, distributed locking and atomic
object-storage operations. It is not built, so do not configure for it.

## 1. Database (Postgres)
1. Provision managed Postgres (Supabase, RDS, Neon, …).
2. `PLANARUS_DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/planarus`
3. Install the driver + migrate: `pip install -e ".[postgres]" && alembic upgrade head`.

## 2. Auth + tenancy
```
PLANARUS_AUTH_ENABLED=true
# do NOT set PLANARUS_AUTH_DEV_LOGIN in production (it's an unauthenticated backdoor)
PLANARUS_WEB_ORIGINS=https://app.yourdomain.com   # your frontend origin(s), CSV
PLANARUS_PROJECTS_ROOT=/srv/planarus/projects      # REQUIRED in auth mode (#115)
```

`PLANARUS_PROJECTS_ROOT` is the server-owned base under which every project's
on-disk folder lives. In auth mode the root is **derived** as
`<PLANARUS_PROJECTS_ROOT>/<workspace_id>/<project_id>` and a tenant can never
choose an arbitrary absolute path — this is the tenant/filesystem isolation
boundary. The app **refuses to start** if auth is on and this is unset (or not
absolute). It must be an absolute path on a writable volume the API process
owns; do not point it at application code, a home directory, or a shared mount.

### Migrating existing project folders

If you enabled auth on a server that already had projects with hand-picked
folders, bring them under the managed base (copy, then repoint — the original is
left in place, so it is reversible):
```
python -m app.jobs adopt-roots            # dry run: prints what would move
python -m app.jobs adopt-roots --apply    # copy + rewrite folder_path
```

## 3. OAuth — register an app per provider
You provide the client id/secret; Planarus has the flow. The **callback/redirect URL**
must be exactly:
```
https://<your-api-host>/api/v1/auth/oauth/<provider>/callback
```

### Google
1. Google Cloud Console → APIs & Services → **Credentials** → *Create OAuth client ID* → **Web application**.
2. Add the callback URL above (`…/oauth/google/callback`) under *Authorized redirect URIs*.
3. Copy the client id/secret:
   ```
   PLANARUS_OAUTH_GOOGLE_CLIENT_ID=...
   PLANARUS_OAUTH_GOOGLE_CLIENT_SECRET=...
   ```

### GitHub
1. GitHub → Settings → Developer settings → **OAuth Apps** → *New OAuth App*.
2. *Authorization callback URL* = the callback above (`…/oauth/github/callback`).
3. Copy the client id + generate a secret:
   ```
   PLANARUS_OAUTH_GITHUB_CLIENT_ID=...
   PLANARUS_OAUTH_GITHUB_CLIENT_SECRET=...
   ```

### Allowlist the callback URLs (required)
Planarus refuses to start any OAuth or calendar-connect flow whose `redirect_uri`
is not in a server-side allowlist (#113) — the URL cannot be taken from the
caller. Set it to every callback you registered above, comma-separated and
matched verbatim:
```
PLANARUS_OAUTH_REDIRECT_URIS=https://<your-api-host>/api/v1/auth/oauth/google/callback,https://<your-api-host>/api/v1/auth/oauth/github/callback
```
Leaving it unset is fail-closed: `…/start` answers **400 redirect_uri is not
allowlisted** and no one can sign in with OAuth. The same variable covers the
calendar connect flow — add those callbacks to the same list.

Install the extra: `pip install -e ".[oauth]"`. A provider that isn't fully
configured simply 404s — you can ship with just one.

### What a sign-in is bound to
Each flow is one server-side, single-use transaction row: it is consumed
atomically by the callback (a replayed or concurrent callback loses), and it is
tied to a short-lived `planarus_oauth_binder` cookie, so a `state` copied out of a
URL or log is useless in another browser. Identity is resolved by the provider's
*subject*, never by email — an account is never linked to a new provider just
because the addresses match. To attach a second provider, sign in first and use
`/api/v1/auth/oauth/<provider>/link/start`. Only a provider-verified email is
accepted (an unverified GitHub address is refused rather than trusted).

## 4. Storage (optional — S3 for generated artifacts)
Local disk is the default and fine for a single API node. For object storage:
```
PLANARUS_STORAGE_BACKEND=s3
PLANARUS_S3_BUCKET=planarus-artifacts
PLANARUS_S3_REGION=us-east-1
# PLANARUS_S3_ENDPOINT_URL=https://...   # for MinIO/R2/other S3-compatibles
```
Credentials come from the standard AWS chain (instance role, `AWS_*` env, etc.).
Install the extra: `pip install -e ".[s3]"`. The IAM principal needs
`s3:GetObject`/`PutObject`/`DeleteObject` (and `HeadObject`) on the bucket.

S3 does not give you multi-node safety: `append_line` is read-modify-write with
no distributed lock, so two instances appending concurrently lose one of the
writes. The §0 single-instance contract is what makes it safe — object storage
buys you durability and a stateless disk, not scale-out.

## 5. Preflight — run the doctor
Before deploying, validate the whole config from the API host:
```
cd apps/api && python scripts/doctor.py
```
It checks the **§0 worker contract** (fails on `WEB_CONCURRENCY`/`UVICORN_WORKERS`
> 1) and prints the topology obligations it cannot verify, that the DB is
reachable **and migrated to head**, that auth is sane (fails if the dev-login
backdoor is on, warns if no web origins), that each configured OAuth provider has
both id + secret, and — for the s3 backend — that the bucket is actually
**writable** (it does a put/read/delete probe). It exits non-zero on any hard
failure, so you can gate your deploy on it.

Run it **on the API host with the deploy's real environment**, not on your
laptop — the worker check reads the env the app will actually boot with.

## 6. Deploy
- **Frontend:** build `apps/web` to static assets → Cloudflare Pages / Vercel.
- **API:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` behind the platform's
  TLS/ingress (Render, Railway, Fly, …); run `alembic upgrade head` on release.
  Use that command **verbatim** — no `--workers`, no gunicorn wrapper — and leave
  `WEB_CONCURRENCY`/`UVICORN_WORKERS` unset (§0). The existing
  `apps/api/Dockerfile` builds a runnable image with exactly this single-process
  `CMD` — it runs as a non-root `planarus` user (#115) and needs its `/data`
  volume and `PLANARUS_PROJECTS_ROOT` writable by that user; its entrypoint fixes
  the bind-mount ownership on start.
- **Platform settings:** set instance/replica count to **1**, turn autoscaling
  **off**, and choose stop-then-start (recreate) over rolling/zero-downtime
  deploys. On Render that is one instance with autoscaling disabled; on Fly,
  `min_machines_running = 1` with no `auto_start`/`auto_stop` scaling group; on
  Railway, a single replica. Point the platform health check at the API and let
  it restart the one instance rather than adding another.

The app still binds loopback by default and never manages its own TLS/tunnel — the
platform fronts it. Rate limiting, the app-wide Host guard, and RFC 9457 errors are
already on — and per §0, that rate limiting is per-process, which is exactly why
the one-process contract is a security property and not a packaging detail.
