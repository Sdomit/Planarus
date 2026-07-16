# Going live: hosted Approvo (OAuth + S3)

Everything hosted is **off by default** — the code is complete and config-driven,
so going live is providing infrastructure and secrets, not writing code. Work
top-to-bottom; the last step (`doctor`) verifies the whole thing before you deploy.

All settings are `AGENTBOARD_*` env vars; `apps/api/deploy/hosted.env.example` is a
fill-in-the-blanks template.

## 1. Database (Postgres)
1. Provision managed Postgres (Supabase, RDS, Neon, …).
2. `AGENTBOARD_DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/approvo`
3. Install the driver + migrate: `pip install -e ".[postgres]" && alembic upgrade head`.

## 2. Auth + tenancy
```
AGENTBOARD_AUTH_ENABLED=true
# do NOT set AGENTBOARD_AUTH_DEV_LOGIN in production (it's an unauthenticated backdoor)
AGENTBOARD_WEB_ORIGINS=https://app.yourdomain.com   # your frontend origin(s), CSV
```

## 3. OAuth — register an app per provider
You provide the client id/secret; Approvo has the flow. The **callback/redirect URL**
must be exactly:
```
https://<your-api-host>/api/v1/auth/oauth/<provider>/callback
```

### Google
1. Google Cloud Console → APIs & Services → **Credentials** → *Create OAuth client ID* → **Web application**.
2. Add the callback URL above (`…/oauth/google/callback`) under *Authorized redirect URIs*.
3. Copy the client id/secret:
   ```
   AGENTBOARD_OAUTH_GOOGLE_CLIENT_ID=...
   AGENTBOARD_OAUTH_GOOGLE_CLIENT_SECRET=...
   ```

### GitHub
1. GitHub → Settings → Developer settings → **OAuth Apps** → *New OAuth App*.
2. *Authorization callback URL* = the callback above (`…/oauth/github/callback`).
3. Copy the client id + generate a secret:
   ```
   AGENTBOARD_OAUTH_GITHUB_CLIENT_ID=...
   AGENTBOARD_OAUTH_GITHUB_CLIENT_SECRET=...
   ```

Install the extra: `pip install -e ".[oauth]"`. A provider that isn't fully
configured simply 404s — you can ship with just one.

## 4. Storage (optional — S3 for generated artifacts)
Local disk is the default and fine for a single API node. For object storage:
```
AGENTBOARD_STORAGE_BACKEND=s3
AGENTBOARD_S3_BUCKET=approvo-artifacts
AGENTBOARD_S3_REGION=us-east-1
# AGENTBOARD_S3_ENDPOINT_URL=https://...   # for MinIO/R2/other S3-compatibles
```
Credentials come from the standard AWS chain (instance role, `AWS_*` env, etc.).
Install the extra: `pip install -e ".[s3]"`. The IAM principal needs
`s3:GetObject`/`PutObject`/`DeleteObject` (and `HeadObject`) on the bucket.

## 5. Preflight — run the doctor
Before deploying, validate the whole config from the API host:
```
cd apps/api && python scripts/doctor.py
```
It checks the DB is reachable **and migrated to head**, that auth is sane
(fails if the dev-login backdoor is on, warns if no web origins), that each
configured OAuth provider has both id + secret, and — for the s3 backend — that
the bucket is actually **writable** (it does a put/read/delete probe). It exits
non-zero on any hard failure, so you can gate your deploy on it.

## 6. Deploy
- **Frontend:** build `apps/web` to static assets → Cloudflare Pages / Vercel.
- **API:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` behind the platform's
  TLS/ingress (Render, Railway, Fly, …); run `alembic upgrade head` on release.
  The existing `apps/api/Dockerfile` builds a runnable image.

The app still binds loopback by default and never manages its own TLS/tunnel — the
platform fronts it. Rate limiting, the app-wide Host guard, and RFC 9457 errors are
already on.
