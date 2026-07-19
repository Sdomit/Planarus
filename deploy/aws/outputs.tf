output "app_url" {
  value       = "https://${var.domain}"
  description = "Where the team signs in once DNS + the TLS cert are live."
}

output "public_ip" {
  value       = aws_eip.app.public_ip
  description = "Point <domain> at this IP (an A record) if you're not using route53_zone_id."
}

output "rds_endpoint" {
  value       = aws_db_instance.this.address
  description = "Managed Postgres host (private; reachable only from the app box)."
}

output "dns_action" {
  value = var.route53_zone_id != "" ? "Route53 A record created for ${var.domain}." : "Create an A record: ${var.domain} -> ${aws_eip.app.public_ip}"
}

output "shell_in" {
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.aws_region}"
  description = "Open a shell on the box (no SSH needed). Then: cd /opt/approvo"
}
