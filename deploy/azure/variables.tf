variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region."
}

variable "resource_group_name" {
  type    = string
  default = "approvo"
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
  sensitive   = true
  description = "git clone URL. Private repo: embed a read-only token, https://x-access-token:TOKEN@github.com/you/AgentBoard.git"
}

variable "repo_branch" {
  type    = string
  default = "main"
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
