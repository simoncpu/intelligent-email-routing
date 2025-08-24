# SES Catch-All Forwarder (Terraform + Python Lambda)

This deploys an Amazon SES inbound pipeline that forwards **any** email sent to `*@<your-domain>` to a single destination (e.g., Gmail).

## What it creates
- Route53 hosted zone for your domain
- S3 bucket to store raw inbound emails
- SES domain identity + DKIM (sending/forwarding) with automatic DNS verification
- SES receipt rule set: S3 store then invoke Lambda
- Python 3.13 Lambda that forwards as a wrapped `message/rfc822` (DMARC-safe)
- All DNS records (MX, TXT, CNAME) automatically configured in Route53

## Prereqs
- AWS account with IAM creds configured: `aws configure`
- Terraform >= 1.6, AWS provider >= 5.40
- Choose an SES **receiving** region (e.g., `us-east-1`)
- **Domain must use Route53 for DNS** - This setup creates a Route53 hosted zone and manages all DNS records automatically

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
3. **Update your domain registrar** to use Route53 nameservers:
   - Get nameservers from: `terraform output nameservers`
   - Log into your domain registrar (GoDaddy, Namecheap, etc.)
   - Update your domain's nameservers to the Route53 nameservers shown in the output
   - DNS propagation typically takes 15 minutes to 48 hours

4. **Verification happens automatically** - Terraform waits for SES domain verification to complete (up to 5 minutes)

5. Test by emailing any address at your domain, e.g. `abc123@example.org`. It should arrive at your `forward_to_email` address.

## Notes
- The Lambda forwards by **sending a new email** via SES with the original message attached as `message/rfc822` and sets `Reply-To` to the original sender.
- Costs: SES receiving ~$0.19 per 1,000 small emails (<=256KB); SES sending $0.10/1k; S3+Lambda minimal at low volume; Route53 hosted zone ~$0.50/month.
- Domain verification happens automatically - Terraform creates all DNS records and waits for SES verification to complete.
- To avoid purging archived mail, disable S3 lifecycle (see comments in `main.tf`).

## Files
- `main.tf`, `variables.tf`, `outputs.tf` - Terraform stack
- `lambda.py` - Python 3.13 Lambda
- `terraform.tfvars` - your values (example provided)

## Contributors
Simon Cornelius P. Umacob
