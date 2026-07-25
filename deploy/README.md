# Planarus — hosted deploy (your own domain)

Team-facing instance on `app.yourdomain.com`, reachable in-office **and** remote from
one deployment.

**One supported artifact: [`docker-compose.hosted.yml`](docker-compose.hosted.yml) +
[`Caddyfile`](Caddyfile).** That stack is built and smoke-tested in CI on every push.
Everything below is where you *place* it — infra + config, no code change beyond Step 0.

> **There is no supported infrastructure-as-code.** The AWS and Azure Terraform modules
> that used to live in `deploy/aws/` and `deploy/azure/` were **retired** (#122); see
> [Retired: the Terraform modules](#retired-the-terraform-modules) at the bottom.
> Cloud placement is manual and is the operator's responsibility.

## The constraint that shapes it: single-origin

The web app calls a **relative** API base (`apps/web/src/api/client.ts` → `const BASE
= '/api/v1'`) and the bundled nginx proxies `/api/` to the backend
(`apps/web/nginx.conf`). There is no configurable API URL. So web + API **must sit
under one hostname** with `/api` routed to the backend. A two-subdomain
(`app.` / `api.`) split would need a frontend change — don't.

## The supported runtime shape: exactly one instance

Pre-1.0 Planarus is supported on **one API process and one replica**, stop-then-start
deploys, autoscaling off. Rate-limit buckets, the local control token, the LAN switch
mirror and presence are all process-local — a second worker multiplies limits and
splits the token. `create_app()` and `scripts/doctor.py` fail closed on
`WEB_CONCURRENCY` / `UVICORN_WORKERS` > 1; replica count and rolling overlap are things
the app **cannot** detect, so they are your obligation. Full contract:
[../docs/guide/hosted-go-live.md](../docs/guide/hosted-go-live.md) §0.

This rules out App Runner, Container Apps with `minReplicas != maxReplicas`, and any
platform that overlaps old and new instances during a deploy.

## Step 0 — the one code change

The shipped image is the SQLite quickstart build (`pip install .` — no driver). Edit
`apps/api/Dockerfile` line 10:

```dockerfile
RUN pip install --no-cache-dir ".[postgres,oauth]"   # add ,s3 if you use S3
```

Harmless to the local/SQLite quickstart (the extra drivers just sit unused).

## Shared config

Copy [`../apps/api/deploy/hosted.env.example`](../apps/api/deploy/hosted.env.example) to
`hosted.env` and fill it in — that file is the single source of truth for the variable
set, kept in step with the code. **Never commit it**; load it from the platform secret
store. Do not re-type the variable list anywhere else; a stale second copy is exactly
what broke the retired Terraform modules.

The three that trip people up:

- `PLANARUS_WEB_ORIGINS` — the exact `https://app.yourdomain.com`.
- `PLANARUS_OAUTH_REDIRECT_URIS` — the exact callback URLs you registered. **Empty means
  every OAuth start is refused**, so nobody can sign in.
- `PLANARUS_EXTERNAL_API_ENABLED=false` — the AI-agent API stays off; exposing it is a
  separately-gated step.

Notes:

- **OAuth callback** (register on the provider, single origin):
  `https://app.yourdomain.com/api/v1/auth/oauth/github/callback`
  GitHub is the quickest (Settings → Developer settings → OAuth Apps). Google works
  the same way. One provider is enough.
- **Migrations** run themselves: the api container's start command does `alembic
  upgrade head`, and `alembic/env.py` picks up `PLANARUS_DATABASE_URL`, so it
  targets Postgres.
- **Preflight gate** — before announcing go-live, run the doctor from the api box and
  require exit 0 (checks DB migrated, auth sane, OAuth complete, S3 writable):
  ```
  docker compose -f docker-compose.hosted.yml run --rm api python scripts/doctor.py
  ```
- **First sign-in becomes admin** (Phase 16 bootstrap); invite the team from the Team
  view. Owners approve agent proposals; editors/viewers as named.

---

## Placement — one VM + compose + managed Postgres

The same recipe on both clouds, because it reuses the CI-proven compose: single-origin,
`/api` proxy and auto-TLS come for free, and one VM is the only shape that honours the
single-instance contract without extra glue.

**Not machine-validated.** No apply/destroy evidence exists in a disposable account.
Treat the steps as a checklist to work through, not a script that is known to run.

1. **Managed Postgres** — AWS RDS `db.t4g.micro` / Azure Flexible Server Burstable
   `B1ms`, DB name `planarus`, private networking, reachable from the app VM only
   (SG allowing `5432` from the VM's SG / VNet integration). Endpoint → `hosted.env`.
2. **VM** — `t3.small` (Amazon Linux 2023 / Ubuntu) or the Azure equivalent, same
   VPC/VNet, static IP. Install Docker + the compose plugin. Give it ~2 GB of swap;
   the Vite web build OOMs on a small box without it.
3. **Firewall** — inbound `80` + `443` from `0.0.0.0/0` (users + Let's Encrypt), `22`
   from your admin IP only.
4. **DNS** — A record `app.yourdomain.com` → the VM's static IP.
5. **Deploy** — get the repo onto the box at a **tag or a pinned commit**, not a moving
   branch. Do Step 0, drop `hosted.env` + `Caddyfile` + `docker-compose.hosted.yml`
   alongside it, then `docker compose -f docker-compose.hosted.yml up -d --build`.
   Caddy issues the cert on first boot. Run the doctor, then sign in.
6. **Secrets** — `hosted.env` root-owned with mode `600` on the box is the floor; move
   to Secrets Manager / SSM Parameter Store / Key Vault if policy requires.
7. **Upgrade** — check out the next pinned tag, `docker compose ... up -d --build`.
   That stops the old container before starting the new one, which is what the
   single-instance contract needs. Take a Postgres snapshot first; there is no tested
   rollback beyond restoring it and checking out the previous tag.

---

## Gotchas checklist

- [ ] Step 0 image extras done, or psycopg2/httpx import fails at boot.
- [ ] Postgres reachable from the API (SG / VNet / firewall) — the #1 hang.
- [ ] `PLANARUS_WEB_ORIGINS` = the exact `https://app.yourdomain.com`.
- [ ] `PLANARUS_OAUTH_REDIRECT_URIS` set, exact match with what the provider has.
- [ ] OAuth callback registered on the provider, exact match.
- [ ] Deployed from a tag/pinned commit, not a moving branch.
- [ ] One VM, one api container, `WEB_CONCURRENCY`/`UVICORN_WORKERS` unset.
- [ ] `STORAGE_BACKEND=local` is per-node → use S3 if generated artifacts must survive
      a rebuild (SQLite would be ephemeral too — this is why Postgres).
- [ ] `doctor.py` exits 0 before you tell the team.
- [ ] `PLANARUS_EXTERNAL_API_ENABLED=false`.

---

## Retired: the Terraform modules

`deploy/aws/` and `deploy/azure/` shipped in #30 with an explicit note that Terraform was
never run against them. They were removed in #122 rather than hardened. What they did,
for anyone reconstructing them:

**Shape** — one Terraform module per cloud, each creating managed Postgres (RDS /
Flexible Server), one VM, a secret store (SSM Parameter Store / Key Vault) read at boot
by an instance role or managed identity, and a cloud-init `user_data` script that
cloned the repo, assembled `hosted.env` from those secrets, and ran the hosted compose.

**Why they were retired, not fixed** — the cloud-init scripts had drifted out of step
with the app and could not sign in at all: neither wrote `PLANARUS_OAUTH_REDIRECT_URIS`,
which #113 made mandatory, so `doctor.py` fails and every OAuth start is refused. They
also each embedded a private copy of the hosted compose (so #120's single-instance
constraint never reached them), `sed`-patched the Dockerfile at boot, cloned a moving
branch, and installed unpinned, unverified binaries from `releases/latest` as root.
Fixing that honestly means CI (`fmt`/`validate`/TFLint/IaC scan), committed provider
locks, an immutable image deployed by digest, encrypted remote state, and real
apply → upgrade → rollback → destroy evidence in disposable accounts. None of that
exists, and unvalidated IaC that *looks* supported is worse than none.

**If you bring them back** — do the above first, and re-derive `hosted.env` from
`apps/api/deploy/hosted.env.example` and the compose from `docker-compose.hosted.yml`
at build time. Do not hand-copy either; that copying is what rotted the originals.
Original source: `git log --all -- deploy/aws deploy/azure`.
