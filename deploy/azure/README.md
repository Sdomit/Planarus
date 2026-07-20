# Approvo on Azure — Terraform (single VM + compose + Flexible Server)

Same shape as the AWS module, Azure-native: one Ubuntu VM runs the CI-proven compose
stack (Caddy → web/nginx → api) behind auto-TLS on your domain; **private** Postgres
Flexible Server (VNet-integrated); secrets in Key Vault, read at boot via a
user-assigned managed identity; shell via `az vm run-command` (no open SSH).
Single-origin, because the frontend requires it.

```
VM (Caddy :443 ─ auto TLS)
  └─ web (nginx: serves SPA, proxies /api) ─► api (FastAPI, :8000)
                                                 └─► Postgres Flexible Server (private, VNet)
```

## Prerequisites
- Terraform ≥ 1.5 and `az login` (a subscription selected).
- A domain you control + ability to add an A record for `<domain>`.
- A **GitHub OAuth app**, callback `https://<domain>/api/v1/auth/oauth/github/callback`.
- An SSH public key (Azure requires one on the VM; the port stays closed by default).
- Private repo? A read-only token — set it as `repo_token` (kept out of `repo_url`).

## Deploy
```bash
cp terraform.tfvars.example terraform.tfvars   # fill in domain, repo_url, SSH key, OAuth
terraform init
terraform apply
```
Then:
1. **DNS** — if you didn't set `dns_zone_name`, create the A record from the
   `dns_action` / `public_ip` output. Caddy can't get a cert until `<domain>` resolves.
2. **Wait** ~4–7 min for cloud-init (installs Docker, clones, applies the
   `[postgres,oauth]` image fix, builds api+web, migrates, Caddy issues TLS). Watch it:
   ```bash
   az vm run-command invoke -g approvo -n approvo --command-id RunShellScript \
     --scripts 'tail -n 80 /var/log/cloud-init-output.log'
   ```
3. **Preflight** — same box, gate on exit 0:
   ```bash
   az vm run-command invoke -g approvo -n approvo --command-id RunShellScript \
     --scripts 'cd /opt/approvo && docker compose -f docker-compose.hosted.yml run --rm api python scripts/doctor.py'
   ```
4. **First sign-in = admin** (Phase 16 bootstrap). Invite the team from the Team view.

## Day 2
- **Update:** `cd /opt/approvo && git pull && docker compose -f docker-compose.hosted.yml up -d --build` (via run-command or SSH).
- **Rotate the GitHub secret:** update the `oauth-github-client-secret` Key Vault secret (or the tfvar + `apply`), then re-run the hosted.env assembly and `up -d`.
- **Teardown:** `terraform destroy`. Snapshot the Flexible Server first if you want to keep the data.

## Deliberate simplifications (ponytail)
- **Single VM, single-zone Postgres.** Production: add `high_availability` on the server
  and a second VM behind a Load Balancer / App Gateway — but that's a different shape.
- **Build on the box** (2GB swap covers the web build). Pre-building to ACR and pulling
  images is the next rung — ask.
- **`STORAGE_BACKEND=local`** on the VM disk; switch to Azure Blob/S3-compatible via the
  `[s3]` extra if artifacts must live off the box.
- **Managed alternative (no VM):** Static Web Apps (SPA) + linked Container Apps (API) +
  Flexible Server is the PaaS route — but SWA content deploy and backend-linking aren't
  cleanly Terraform-able, and Container Apps alone would force an nginx.conf rewrite for
  the relative `/api` frontend. That's why this module uses the VM. Say so if you want
  the PaaS version done via `az`/portal instead.
- The **external AI-agent API stays off** — exposing it is a separate, gated step.
