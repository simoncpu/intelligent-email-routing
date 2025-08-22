output "bucket_name" {
  value = aws_s3_bucket.mail.bucket
  description = "S3 bucket where raw emails are stored"
}

output "ses_domain_verification_token" {
  value = aws_ses_domain_identity.this.verification_token
  description = "Create TXT at _amazonses.${var.domain_name} with this value"
}

output "dkim_tokens" {
  value = aws_ses_domain_dkim.this.dkim_tokens
  description = "Create 3 CNAMEs: <token>._domainkey.${var.domain_name} -> <token>.dkim.amazonses.com"
}

output "mx_record_value" {
  value = "10 inbound-smtp.${var.region}.amazonaws.com"
  description = "Create MX on ${var.domain_name} with this value"
}

output "from_address_to_verify" {
  value       = "forwarder@${var.domain_name}"
  description = "Optional: verify this SES identity too (domain verification generally covers it)"
}
