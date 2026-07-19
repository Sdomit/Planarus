# Approvo on AWS — Terraform (single VM + compose + RDS)

Stands up: RDS Postgres, one EC2 app box running the CI-proven compose stack
(Caddy → web/nginx → api) behind auto-TLS on your domain, secrets in SSM, shell via
Session Manager (no open SSH). Single-origin, because the frontend requires it.

```
EC2 (Caddy :443 ─ auto TLS)
  └─ web (nginx: serves SPA, proxies /api) ─► api (FastAPI, :8000)
                                                 └─► RDS Postgres (private)
```

## Prerequisites
- Terraform ≥ 1.5, AWS credentials with rights to make EC2/RDS/IAM/SSM (+ Route53 if used).
- A domain you control, and the ability to add an A record for `<domain>`.
- A **GitHub OAuth app** with callback `https://<domain>/api/v1/auth/oauth/github/callback`.
- If the repo is private, a read-only token to embed in `repo_url`.

## Deploy
```bash
cp terraform.tfvars.example terraform.tfvars   # fill in domain, repo_url, GitHub OAuth
terraform init
terraform apply
```
Then:
1. **DNS** — if you didn't set `route53_zone_id`, create the A record from the
   `dns_action` / `public_ip` output. Caddy can't get a cert until `<domain>` resolves
   to the box.
2. **Wait** ~3–6 min for cloud-init: it installs Docker, clones the repo, applies the
   `[postgres,oauth]` image fix, builds api+web, runs `alembic upgrade head`, and Caddy
   issues the TLS cert. Watch it:
   ```bash
   aws ssm start-session --target <instance-id>        # from the shell_in output
   sudo tail -f /var/log/cloud-init-output.log
   ```
3. **Preflight** — from the box:
   ```bash
   cd /opt/approvo
   docker compose -f docker-compose.hosted.yml run --rm api python scripts/doctor.py
   ```
   Require exit 0 before you hand it to the team.
4. **First sign-in = admin** (Phase 16 bootstrap). Invite the team from the Team view.

## Day 2
- **Update to a new version:** on the box, `cd /opt/approvo && git pull && docker compose
  -f docker-compose.hosted.yml up -d --build`.
- **Logs:** `docker compose -f docker-compose.hosted.yml logs -f api`
- **Rotate the GitHub secret:** update the SSM param, then re-run the hosted.env assembly
  (or just `terraform apply` after changing the tfvar) and `up -d`.
- **Teardown:** `terraform destroy`. (RDS `skip_final_snapshot=true` — take a manual
  snapshot first if you want to keep the data.)

## Deliberate simplifications (ponytail)
- **Default VPC**, single-AZ RDS, destroyable DB. For production: dedicated VPC,
  `multi_az=true`, `deletion_protection=true`, a final snapshot — all one-line flips in
  `main.tf`.
- **Build on the box** (2GB swap added so the web build doesn't OOM). If you'd rather
  pre-build and pull images from ECR, that's the next rung — ask.
- **`STORAGE_BACKEND=local`** on the box's disk. Fine for generated artifacts on a
  single node; switch to S3 (`.[s3]` extra + bucket) if you scale out or want them off
  the box.
- The **external AI-agent API stays off**. Exposing it is a separate, deliberately-gated
  step.
