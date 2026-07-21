variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region."
}

variable "resource_group_name" {
  type    = string
  default = "planarus"
}

variable "domain" {
  type        = string
  description = "Full hostname the team uses, e.g. app.yourcompany.com. Caddy issues TLS for exactly this name."
}

variable "vm_size" {
  type        = string
  default     = "Standard_B2s"
  description = "2 vCPU / 4GB — enough to build the web image. A 2GB swap is added regardless."
}

variable "admin_username" {
  type    = string
  default = "azureadmin"
}

variable "admin_ssh_public_key" {
  type        = string
  description = "SSH public key for the VM admin (Azure requires one). Port 22 stays CLOSED unless admin_cidr is set — shell via 'az vm run-command' otherwise."
}

variable "admin_cidr" {
  type        = string
  default     = ""
  description = "If set, opens SSH (22) to this CIDR only, e.g. 203.0.113.4/32. Empty = no inbound SSH."
}

variable "repo_url" {
  type        = string
  description = "Plain HTTPS clone URL, NO credentials in it, e.g. https://github.com/you/Planarus.git. Public repos clone as-is; for a private repo set repo_token instead of embedding a token here."
}

variable "repo_branch" {
  type    = string
  default = "main"
}

variable "repo_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Read-only token for a PRIVATE repo. Stored in Key Vault and fetched at boot; the VM injects it via git's config env so it never lands in the clone URL, process args, .git/config, the cloud-init log, or the instance custom-data. Leave empty for a public repo."
}

variable "github_client_id" {
  type        = string
  description = "GitHub OAuth app client id. Callback: https://<domain>/api/v1/auth/oauth/github/callback"
}

variable "github_client_secret" {
  type      = string
  sensitive = true
}

# Optional: create the A record in an Azure DNS zone you already host.
variable "dns_zone_name" {
  type    = string
  default = ""
}
variable "dns_zone_resource_group" {
  type    = string
  default = ""
}
variable "dns_record_name" {
  type        = string
  default     = "app"
  description = "Record label within dns_zone_name (only used when dns_zone_name is set)."
}
