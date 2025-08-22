# SES Catch-All Forwarder (Terraform + Python Lambda)

This deploys an Amazon SES inbound pipeline that forwards **any** email sent to `*@<your-domain>` to a single destination (e.g., Gmail).

## What it creates
- S3 bucket to store raw inbound emails
- SES domain identity + DKIM (sending/forwarding)
- SES receipt rule set: S3 store then invoke Lambda
- Python 3.13 Lambda that forwards as a wrapped `message/rfc822` (DMARC-safe)

## Prereqs
- AWS account with IAM creds configured: `aws configure`
- Terraform >= 1.6, AWS provider >= 5.40
- Choose an SES **receiving** region (e.g., `us-east-1`)

## Quick start
1. Edit `terraform.tfvars`:
   ```hcl
   domain_name      = "example.org"
   forward_to_email = "myrealemail@gmail.com"
   region           = "us-east-1"
   ```
2. Init and apply:
   ```bash
   terraform init
   terraform apply
   ```
3. **Add DNS** at your DNS host (NOT automatically managed here):
   - **MX**: `10 inbound-smtp.<region>.amazonaws.com` on `example.org`
   - **TXT (SES verify)**: name `_amazonses.example.org`, value is shown in Terraform outputs
   - **CNAME (DKIM x3)**: tokens shown in Terraform outputs -> `*.dkim.amazonses.com`
   - **TXT (SPF)**: for example `v=spf1 include:amazonses.com -all`
   - **TXT (DMARC)**: for example `v=DMARC1; p=quarantine; rua=mailto:dmarc@example.org; ruf=mailto:dmarc@example.org; fo=1`

   After DNS propagates (a few minutes), SES will mark the domain + DKIM **verified**.

4. Test by emailing any address at your domain, e.g. `abc123@example.org`. It should arrive at your `forward_to_email` address.

## Notes
- The Lambda forwards by **sending a new email** via SES with the original message attached as `message/rfc822` and sets `Reply-To` to the original sender.
- Costs: SES receiving ~$0.19 per 1,000 small emails (<=256KB); SES sending $0.10/1k; S3+Lambda minimal at low volume.
- If your domain is *not* verified yet, delivery won't occur - add the DNS records first. You can keep running `terraform apply` as you verify.
- To purge archived mail, enable S3 lifecycle (see comments in `main.tf`).

## Files
- `main.tf`, `variables.tf`, `outputs.tf` - Terraform stack
- `lambda.py` - Python 3.13 Lambda
- `terraform.tfvars` - your values (example provided)
