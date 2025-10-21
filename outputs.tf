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

output "lambda_function_name" {
  value       = aws_lambda_function.forwarder.function_name
  description = "Lambda function name for email forwarding"
}

output "lambda_log_group_name" {
  value       = aws_cloudwatch_log_group.lambda_logs.name
  description = "CloudWatch log group name for email forwarder Lambda"
}

output "mcp_function_name" {
  value       = aws_lambda_function.mcp_server.function_name
  description = "MCP server Lambda function name"
}

output "mcp_log_group_name" {
  value       = aws_cloudwatch_log_group.mcp_lambda_logs.name
  description = "CloudWatch log group name for MCP server Lambda"
}
