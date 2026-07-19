output "app_url" {
  value       = "https://${var.domain}"
  description = "Where the team signs in once DNS + the TLS cert are live."
}

output "public_ip" {
  value       = azurerm_public_ip.vm.ip_address
  description = "Point <domain> at this IP (an A record) if you're not using dns_zone_name."
}

output "postgres_fqdn" {
  value       = azurerm_postgresql_flexible_server.this.fqdn
  description = "Managed Postgres host (private; resolvable only inside the VNet)."
}

output "dns_action" {
  value = var.dns_zone_name != "" ? "Azure DNS A record created: ${var.dns_record_name}.${var.dns_zone_name}" : "Create an A record: ${var.domain} -> ${azurerm_public_ip.vm.ip_address}"
}

output "shell_in" {
  value       = "az vm run-command invoke -g ${var.resource_group_name} -n approvo --command-id RunShellScript --scripts 'tail -n 80 /var/log/cloud-init-output.log'"
  description = "Watch the bootstrap without opening SSH. (Or set admin_cidr and ssh in as the admin user.)"
}
