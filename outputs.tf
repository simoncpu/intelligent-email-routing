output "bucket_name" {
  value       = aws_s3_bucket.mail.bucket
  description = "S3 bucket where raw emails are stored"
}

output "hosted_zone_id" {
  value       = data.aws_route53_zone.main.zone_id
  description = "Route53 hosted zone ID for the domain"
}

output "nameservers" {
  value       = data.aws_route53_zone.main.name_servers
  description = "Route53 nameservers from existing hosted zone"
}

output "domain_verification_status" {
  value       = aws_ses_domain_identity_verification.this.id
  description = "SES domain verification status - shows domain is verified"
}

output "from_address" {
  value       = "forwarder@${var.domain_name}"
  description = "Verified sender address for forwarded emails"
}

output "mcp_server_url" {
  value       = aws_lambda_function_url.mcp_server.function_url
  description = "MCP server URL for Claude Desktop configuration"
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.routing.name
  description = "DynamoDB table name for AI routing configuration"
}
