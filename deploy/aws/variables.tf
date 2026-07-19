variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "Region to deploy into."
}

variable "domain" {
  type        = string
  description = "Full hostname the team will use, e.g. app.yourcompany.com. Caddy issues TLS for exactly this name."
}

variable "instance_type" {
  type        = string
  default     = "t3.small"
  description = "EC2 size. t3.small (2GB) builds fine with the 2GB swap cloud-init adds; bump to t3.medium if builds drag."
}

variable "repo_url" {
  type        = string
  description = "git clone URL for the Approvo repo. For a PRIVATE repo embed a token: https://x-access-token:TOKEN@github.com/you/AgentBoard.git"
  sensitive   = true
}

variable "repo_branch" {
  type        = string
  default     = "main"
  description = "Branch to deploy."
}

variable "github_client_id" {
  type        = string
  description = "GitHub OAuth app client id. Callback must be https://<domain>/api/v1/auth/oauth/github/callback"
}

variable "github_client_secret" {
  type      = string
  sensitive = true
}

variable "route53_zone_id" {
  type        = string
  default     = ""
  description = "If set, an A record <domain> -> instance is created. Leave empty to point DNS yourself."
}

variable "ssh_key_name" {
  type        = string
  default     = ""
  description = "Optional EC2 key pair name to enable SSH on 22 (from admin_cidr). Empty = no SSH; use SSM Session Manager instead."
}

variable "admin_cidr" {
  type        = string
  default     = ""
  description = "CIDR allowed to SSH (only used when ssh_key_name is set), e.g. 203.0.113.4/32."
}

variable "ssm_prefix" {
  type        = string
  default     = "/approvo"
  description = "SSM Parameter Store path prefix for the secrets the instance reads at boot."
}
