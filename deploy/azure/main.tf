terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.100" }
    random  = { source = "hashicorp/random", version = "~> 3.5" }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
}

# --- Network: VM subnet + a delegated subnet for private Postgres -------------
resource "azurerm_virtual_network" "this" {
  name                = "approvo-vnet"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = ["10.20.0.0/16"]
}

resource "azurerm_subnet" "vm" {
  name                 = "vm"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.20.1.0/24"]
}

resource "azurerm_subnet" "pg" {
  name                 = "postgres"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.20.2.0/24"]
  delegation {
    name = "fs"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "pg" {
  name                = "approvo.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  name                  = "approvo-pg"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name  = azurerm_private_dns_zone.pg.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

# --- Managed Postgres (private, VNet-integrated) ------------------------------
resource "random_password" "db" {
  length  = 24
  special = false # ponytail: alnum only — drops into the DSN with no %-encoding
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                = "approvo-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  version             = "16"
  administrator_login = "approvo"
  administrator_password = random_password.db.result
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  delegated_subnet_id = azurerm_subnet.pg.id
  private_dns_zone_id = azurerm_private_dns_zone.pg.id
  zone                = "1"
  # ponytail: single zone, no HA. Production: high_availability { mode = "ZoneRedundant" }.
  depends_on = [azurerm_private_dns_zone_virtual_network_link.pg]
}

resource "azurerm_postgresql_flexible_server_database" "approvo" {
  name      = "approvo"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# --- Secrets: Key Vault + a user-assigned identity the VM uses to read them ----
# User-assigned (not system-assigned) so the access policy exists BEFORE the VM
# boots and cloud-init fetches — no chicken/egg.
resource "azurerm_user_assigned_identity" "vm" {
  name                = "approvo-vm"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
}

resource "azurerm_key_vault" "this" {
  name                = "approvo-kv-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
}

resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id       = azurerm_key_vault.this.id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  object_id          = data.azurerm_client_config.current.object_id
  secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
}

resource "azurerm_key_vault_access_policy" "vm" {
  key_vault_id       = azurerm_key_vault.this.id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  object_id          = azurerm_user_assigned_identity.vm.principal_id
  secret_permissions = ["Get", "List"]
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  key_vault_id = azurerm_key_vault.this.id
  value        = "postgresql+psycopg2://approvo:${random_password.db.result}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/approvo?sslmode=require"
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "gh_id" {
  name         = "oauth-github-client-id"
  key_vault_id = azurerm_key_vault.this.id
  value        = var.github_client_id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "gh_secret" {
  name         = "oauth-github-client-secret"
  key_vault_id = azurerm_key_vault.this.id
  value        = var.github_client_secret
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

# Private-repo clone token. Created only when set; the box reads it at boot the
# same way it reads the other secrets, so it never rides in the custom-data.
resource "azurerm_key_vault_secret" "repo_token" {
  count        = var.repo_token == "" ? 0 : 1
  name         = "repo-token"
  key_vault_id = azurerm_key_vault.this.id
  value        = var.repo_token
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

# --- The app box --------------------------------------------------------------
resource "azurerm_network_security_group" "vm" {
  name                = "approvo-vm"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name

  security_rule {
    name                       = "web"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  dynamic "security_rule" {
    for_each = var.admin_cidr != "" ? [1] : []
    content {
      name                       = "ssh"
      priority                   = 110
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "22"
      source_address_prefix      = var.admin_cidr
      destination_address_prefix = "*"
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "vm" {
  subnet_id                 = azurerm_subnet.vm.id
  network_security_group_id = azurerm_network_security_group.vm.id
}

resource "azurerm_public_ip" "vm" {
  name                = "approvo-vm"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "vm" {
  name                = "approvo-vm"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.vm.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vm.id
  }
}

resource "azurerm_linux_virtual_machine" "vm" {
  name                  = "approvo"
  resource_group_name   = azurerm_resource_group.this.name
  location              = azurerm_resource_group.this.location
  size                  = var.vm_size
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.vm.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.admin_ssh_public_key
  }
  disable_password_authentication = true

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  custom_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    domain        = var.domain
    repo_url      = var.repo_url
    repo_branch   = var.repo_branch
    kv_uri        = azurerm_key_vault.this.vault_uri
    uai_client_id = azurerm_user_assigned_identity.vm.client_id
    # A boolean, never the token itself — the value stays in Key Vault, off the box's custom-data.
    repo_token_configured = var.repo_token != ""
  }))

  # Boot only after Postgres is up and the secrets + read access exist.
  depends_on = [
    azurerm_key_vault_secret.database_url,
    azurerm_key_vault_secret.gh_id,
    azurerm_key_vault_secret.gh_secret,
    azurerm_key_vault_secret.repo_token, # empty list when no token — still a valid dependency
    azurerm_key_vault_access_policy.vm,
  ]
}

# --- Optional DNS -------------------------------------------------------------
resource "azurerm_dns_a_record" "app" {
  count               = var.dns_zone_name != "" ? 1 : 0
  name                = var.dns_record_name
  zone_name           = var.dns_zone_name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = 300
  records             = [azurerm_public_ip.vm.ip_address]
}
