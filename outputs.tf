output "bucket_name" {
  value = aws_s3_bucket.mail.bucket
  description = "S3 bucket where raw emails are stored"
}

output "ses_domain_verification_token" {
  value = aws_ses_domain_identity.this.verification_token
  description = "Domain verification token for SES"
}

output "dkim_tokens" {
  value = aws_ses_domain_dkim.this.dkim_tokens
  description = "DKIM tokens for SES domain verification"
}

output "mx_record_value" {
  value = "10 inbound-smtp.${var.region}.amazonaws.com"
  description = "MX record value for your domain"
}

output "from_address_to_verify" {
  value       = "forwarder@${var.domain_name}"
  description = "Optional SES email identity to verify"
}
