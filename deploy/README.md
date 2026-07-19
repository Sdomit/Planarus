# Approvo — hosted deploy on AWS & Azure (your own domain)

Team-facing instance on `app.yourdomain.com`, reachable in-office **and** remote from
one deployment. Everything below is infra + config; the only code change is one line.

## The constraint that shapes it: single-origin

The web app calls a **relative** API base (`apps/web/src/api/client.ts` → `const BASE
= '/api/v1'`) and the bundled nginx proxies `/api/` to the backend
(`apps/web/nginx.conf`). There is no configurable API URL. So web + API **must sit
under one hostname** with `/api` routed to the backend. A two-subdomain
(`app.` / `api.`) split would need a frontend change — don't.

## Step 0 — the one code change (both clouds, all shapes)

The shipped image is the SQLite quickstart build (`pip install .` — no driver). Edit
`apps/api/Dockerfile` line 10:

```dockerfile
RUN pip install --no-cache-dir ".[postgres,oauth]"   # add ,s3 if you use S3
```

Harmless to the local/SQLite quickstart (the extra drivers just sit unused).

## Shared config (both clouds)

`hosted.env` (load via the platform secret store; **never commit**):

```
AGENTBOARD_DATABASE_URL=postgresql+psycopg2://USER:PASS@<pg-host>:5432/approvo
AGENTBOARD_AUTH_ENABLED=true
AGENTBOARD_WEB_ORIGINS=https://app.yourdomain.com
AGENTBOARD_OAUTH_GITHUB_CLIENT_ID=...
AGENTBOARD_OAUTH_GITHUB_CLIENT_SECRET=...
AGENTBOARD_STORAGE_BACKEND=local          # S3 optional; local disk is fine for one node
AGENTBOARD_EXTERNAL_API_ENABLED=false     # AI-agent API stays OFF — separate later step
```

- **OAuth callback** (register on the provider, single origin):
  `https://app.yourdomain.com/api/v1/auth/oauth/github/callback`
  GitHub is the quickest (Settings → Developer settings → OAuth Apps). Google works
  the same way. One provider is enough.
- **Migrations** run themselves: the api container's start command does `alembic
  upgrade head`, and `alembic/env.py` picks up `AGENTBOARD_DATABASE_URL`, so it
  targets Postgres.
- **Preflight gate** — before announcing go-live, run the doctor from the api box and
  require exit 0 (checks DB migrated, auth sane, OAuth complete, S3 writable):
  ```
  docker compose -f docker-compose.hosted.yml run --rm api python scripts/doctor.py
  ```
- **First sign-in becomes admin** (Phase 16 bootstrap); invite the team from the Team
  view. Owners approve agent proposals; editors/viewers as named.

---

## AWS — recommended: one VM + compose + RDS

The lazy-correct AWS shape. Reuses the CI-proven compose (`docker-compose.hosted.yml`
+ `Caddyfile`, attached), so single-origin + `/api` proxy + auto-TLS come for free and
you avoid the App Runner↔CloudFront cookie/host glue.

1. **RDS PostgreSQL** — `db.t4g.micro`, private subnets, DB name `approvo`. SG: allow
   `5432` from the EC2 instance's SG only. Put the endpoint in `hosted.env`.
2. **EC2** — `t3.small`, Amazon Linux 2023 or Ubuntu, in the same VPC. Install Docker
   + the compose plugin. Attach an Elastic IP.
3. **Security group (EC2)** — inbound `80` + `443` from `0.0.0.0/0` (users + Let's
   Encrypt), `22` from your admin IP only.
4. **DNS** — Route 53 (or your registrar) A record `app.yourdomain.com` → the Elastic
   IP.
5. **Deploy** — get the repo onto the box (git clone), do Step 0, drop `hosted.env` +
   `Caddyfile` + `docker-compose.hosted.yml` alongside it, then
   `docker compose -f docker-compose.hosted.yml up -d --build`. Caddy issues the cert
   on first boot. Run the doctor (above), then sign in.
6. **Secrets** — `hosted.env` root-owned on the box is fine to start; move to Secrets
   Manager / SSM Parameter Store if policy requires.

*Managed/no-VM alternative:* App Runner (API, VPC connector → RDS) + S3/CloudFront for
the SPA with a `/api/*` behavior routed to App Runner. Single-origin works, but you
must forward cookies + the right host header through CloudFront to keep sessions —
more glue than the VM. Say the word and I'll write it.

---

## Azure — recommended: Static Web Apps + Container Apps + Flexible Server

Azure has a purpose-built single-origin path, so no VM to patch. Static Web Apps
serves the SPA and **reserves `/api`** as a proxy to a linked backend — which is
exactly the app's `/api/v1` base. No CORS, one domain, free managed TLS.

1. **Postgres Flexible Server** — Burstable `B1ms`, DB `approvo`. Networking: private
   (VNet-integrated) is best; "public + firewall allow Azure services" is the quick
   start. Endpoint → `hosted.env`.
2. **Container Apps** — create an environment; build the api image (Step 0) and push
   to ACR; deploy it with external ingress on port `8000` and the `hosted.env` values
   as env vars/secrets. This is the backend SWA will link.
3. **Static Web Apps (Standard plan)** — deploy the `apps/web` build (SWA CLI or the
   GitHub Action). Add custom domain `app.yourdomain.com` (free managed cert). **Link
   the Container App as the backend** so `/api/*` proxies to it (single origin).
4. **OAuth callback** — `https://app.yourdomain.com/api/v1/auth/oauth/github/callback`
   (SWA proxies it through to the Container App).
5. Run the doctor against the Flexible Server, gate on exit 0, sign in (first user =
   admin).

Caveats to verify on your tenant: SWA linked-backend needs the **Standard** plan and
forwards cookies same-origin (sessions work), but the SWA proxy has request
timeout/size limits — fine for normal app use; the AI-agent API stays off regardless.

*Fallback:* the same VM + compose recipe as AWS works on an Azure VM + Flexible Server
if you'd rather not wire SWA ↔ Container Apps.

---

## Gotchas checklist

- [ ] Step 0 image extras done, or psycopg2/httpx import fails at boot.
- [ ] Postgres reachable from the API (SG / VNet / firewall) — the #1 hang.
- [ ] `AGENTBOARD_WEB_ORIGINS` = the exact `https://app.yourdomain.com`.
- [ ] OAuth callback registered on the provider, exact match.
- [ ] `STORAGE_BACKEND=local` is per-node ephemeral on serverless runners → use S3 if
      generated artifacts must survive redeploys (SQLite would be ephemeral too — this
      is why Postgres).
- [ ] `doctor.py` exits 0 before you tell the team.
- [ ] `AGENTBOARD_EXTERNAL_API_ENABLED=false` — exposing the AI-agent API is its own
      deliberate, separately-gated step.
