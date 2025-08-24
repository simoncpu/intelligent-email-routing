output "bucket_name" {
  value = aws_s3_bucket.mail.bucket
  description = "S3 bucket where raw emails are stored"
}

output "from_address_to_verify" {
  value       = "forwarder@${var.domain_name}"
  description = "Optional SES email identity to verify"
}

#####################################################
# DNS RECORDS TO ADD AT YOUR DOMAIN REGISTRAR
#####################################################

output "dns_records_to_add" {
  value = <<-EOT
    
    === DNS RECORDS TO ADD AT YOUR DOMAIN REGISTRAR ===
    
    1. MX RECORD (Required for receiving emails):
       Name: ${var.domain_name}
       Type: MX
       Value: 10 inbound-smtp.${var.region}.amazonaws.com
       TTL: 300
    
    2. TXT RECORD (Required for domain verification):
       Name: _amazonses.${var.domain_name}
       Type: TXT
       Value: ${aws_ses_domain_identity.this.verification_token}
       TTL: 300
    
    3. DKIM CNAME RECORDS (Required for email authentication):
       ${join("\n       ", formatlist("Name: %s._domainkey.%s\n       Type: CNAME\n       Value: %s.dkim.amazonses.com\n       TTL: 300", aws_ses_domain_dkim.this.dkim_tokens, var.domain_name, aws_ses_domain_dkim.this.dkim_tokens))}
    
    4. SPF TXT RECORD (Recommended for email deliverability):
       Name: ${var.domain_name}
       Type: TXT
       Value: "v=spf1 include:amazonses.com -all"
       TTL: 300
    
    5. DMARC TXT RECORD (Recommended for email security):
       Name: _dmarc.${var.domain_name}
       Type: TXT
       Value: "v=DMARC1; p=quarantine; rua=mailto:dmarc@${var.domain_name}"
       TTL: 300
    
    =========================================================
    
  EOT
  description = "Complete DNS records to add at your domain registrar"
}

output "mx_record_value" {
  value = "10 inbound-smtp.${var.region}.amazonaws.com"
  description = "MX record value for your domain"
}

output "ses_domain_verification_token" {
  value = aws_ses_domain_identity.this.verification_token
  description = "Domain verification token for SES"
}

output "dkim_tokens" {
  value = aws_ses_domain_dkim.this.dkim_tokens
  description = "DKIM tokens for SES domain verification"
}
