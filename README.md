# Artificial Intelligence E-mail Agent using AWS SES

This deploys an Amazon SES inbound pipeline that forwards **any** email sent to `*@<your-domain>` to a single destination (e.g., Gmail).

**AI-Powered Routing (Optional)**: Uses AWS Bedrock Claude Sonnet 4.5 to intelligently analyze, classify, and route emails based on content. Can automatically add tags, detect urgency, analyze sentiment, and route to different recipients.

**Multi-Domain Support**: You can use this setup for multiple domains in the same AWS account. Each domain gets its own resources (Lambda, S3 bucket) but shares a common SES receipt rule set.

## What it creates
- Route53 hosted zone for your domain
- S3 bucket to store raw inbound emails (one per domain)
- SES domain identity + DKIM (sending/forwarding) with automatic DNS verification
- SES receipt rule added to shared rule set (ses-catchall-forwarder-rules)
- Python 3.13 Lambda function (one per domain)
- DynamoDB table for AI routing configuration (when AI routing enabled)
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
   forward_to_email = "example@gmail.com"
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

## Setting up multiple domains

If you want to forward emails for multiple domains (e.g., `domain1.example.com` and `domain2.example.org`), follow these steps:

### First domain setup
1. Clone this repository to a folder named after your first domain:
   ```bash
   git clone <repo-url> domain1-email-forwarder
   cd domain1-email-forwarder
   ```

2. Create `terraform.tfvars` with your first domain:
   ```hcl
   project_name     = "domain1-forwarder"  # Unique name for this domain
   domain_name      = "domain1.example.com"
   forward_to_email = "your@gmail.com"
   region           = "us-east-1"
   s3_bucket        = "your-domain1-emails"
   dmarc_rua_email  = "your-dmarc@example.com"
   ```

3. Deploy:
   ```bash
   terraform init
   terraform apply
   ```

### Second domain setup
1. Clone the repository again to a different folder:
   ```bash
   git clone <repo-url> domain2-email-forwarder
   cd domain2-email-forwarder
   ```

2. Create `terraform.tfvars` with your second domain:
   ```hcl
   project_name     = "domain2-forwarder"  # Different from first domain!
   domain_name      = "domain2.example.org"
   forward_to_email = "your@gmail.com"
   region           = "us-east-1"          # Must be same region as first domain
   s3_bucket        = "your-domain2-emails"  # Different bucket name
   dmarc_rua_email  = "your-dmarc@example.com"
   ```

3. Deploy:
   ```bash
   terraform init
   terraform apply
   ```

### Important notes for multi-domain setup
- **Use different `project_name`** for each domain to avoid resource naming conflicts
- **Use the same AWS region** for all domains (SES has only one active rule set per region)
- **Use different S3 bucket names** for each domain
- Each domain gets its own Lambda function, S3 bucket, and DynamoDB table
- All domains share the same SES receipt rule set (`ses-catchall-forwarder-rules`)
- Keep each domain's Terraform state in separate directories

## AI Routing (Optional)

To enable AI-powered email routing:

1. Enable Bedrock model access in AWS console:
   - Navigate to AWS Bedrock console > Model access
   - Enable "Claude Sonnet 4.5" model

2. Set `ai_routing_enabled = true` in terraform.tfvars

3. Configure routing rules in DynamoDB (see [email-copilot.md](email-copilot.md) for details)

4. Test by sending emails - Claude Sonnet 4.5 will analyze and route them based on your rules

Additional costs when AI routing enabled: ~$0.50-1.00/month for 1,000 emails (Bedrock Claude Sonnet 4.5 + DynamoDB).

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
