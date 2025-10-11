# AI Email Agent - Intelligent Email Forwarding with AWS SES

An intelligent email forwarding system that routes emails sent to `*@yourdomain.org` to your destination address (e.g., Gmail). Uses AWS Bedrock Claude to intelligently analyze and route emails based on content.

## Features

- **Catch-all forwarding**: Forward any email sent to your domain
- **AI-powered routing** (optional): Automatically classify, tag, and route emails using Claude Sonnet 4.5
- **Multi-domain support**: Manage multiple domains in the same AWS account
- **Automated DNS setup**: All DNS records configured automatically via Route53
- **DMARC/SPF compliant**: Preserves email authentication and deliverability
- **Production-ready**: Includes logging, monitoring, and error handling

## What Gets Deployed

When you run `terraform apply`, these AWS resources are created:

- **Route53**: Uses your existing hosted zone for DNS management
- **S3 bucket**: Stores raw inbound emails (30-day retention by default)
- **SES domain identity**: Verifies your domain and configures DKIM
- **Lambda function**: Python 3.13 function that processes and forwards emails
- **DynamoDB table**: Stores AI routing configuration (when AI routing enabled)
- **IAM roles/policies**: Minimal permissions for Lambda execution
- **CloudWatch logs**: 30-day retention for debugging

All DNS records (MX, TXT, CNAME, DMARC) are automatically configured.

## Prerequisites

- AWS account with credentials configured (`aws configure`)
- Terraform >= 1.6, AWS provider >= 5.40
- **Domain using Route53 for DNS** (existing hosted zone required)
- SES receiving region (use `us-east-1` for widest availability)

## Quick Start

### 1. Configure Your Settings

Create `terraform.tfvars` with your domain and email settings:

```hcl
domain_name      = "example.org"
forward_to_email = "your@gmail.com"
region           = "us-east-1"
s3_bucket        = "my-email-bucket"
dmarc_rua_email  = "re+xxxxx@dmarc.postmarkapp.com"
```

Get your free DMARC reporting email from https://dmarc.postmarkapp.com/

### 2. Deploy Infrastructure

```bash
# Initialize Terraform (first time only)
terraform init

# Preview changes
terraform plan

# Deploy
terraform apply
```

Terraform will automatically:
- Configure all DNS records in Route53
- Verify your domain with SES (waits up to 5 minutes)
- Deploy Lambda function and S3 bucket
- Create DynamoDB table for AI routing

### 3. Test Email Forwarding

Send a test email to any address at your domain:

```bash
echo "Test message" | mail -s "Test" test@example.org
```

The email should arrive at your `forward_to_email` address within seconds.

## Setting Up Multiple Domains

You can forward emails for multiple domains in the same AWS account:

### First Domain

```bash
git clone <repo-url> domain1-email-forwarder
cd domain1-email-forwarder

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
project_name     = "domain1-forwarder"
domain_name      = "domain1.com"
forward_to_email = "your@gmail.com"
region           = "us-east-1"
s3_bucket        = "domain1-emails"
dmarc_rua_email  = "re+xxxxx@dmarc.postmarkapp.com"
EOF

terraform init && terraform apply
```

### Second Domain

```bash
git clone <repo-url> domain2-email-forwarder
cd domain2-email-forwarder

# Create terraform.tfvars with DIFFERENT values
cat > terraform.tfvars <<EOF
project_name     = "domain2-forwarder"  # Must be different!
domain_name      = "domain2.org"
forward_to_email = "your@gmail.com"
region           = "us-east-1"          # Same region as first domain
s3_bucket        = "domain2-emails"     # Must be different!
dmarc_rua_email  = "re+xxxxx@dmarc.postmarkapp.com"
EOF

terraform init && terraform apply
```

**Important notes**:
- Use **different `project_name`** for each domain
- Use the **same `region`** for all domains
- Use **different S3 bucket names** for each domain
- Keep each domain's Terraform state in separate directories

## AI-Powered Routing (Optional)

Enable intelligent email routing using AWS Bedrock Claude:

### 1. Enable Bedrock Model Access

```bash
# Open Bedrock console
open https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess

# Enable "Claude Sonnet 4.5" model access (click checkbox and save)
```

### 2. Enable AI Routing

Add to your `terraform.tfvars`:

```hcl
ai_routing_enabled = true
```

Then apply:

```bash
terraform apply
```

### 3. Configure Routing Rules

Add a routing prompt to DynamoDB:

```bash
# Get your table name
TABLE_NAME=$(terraform output -raw dynamodb_table_name 2>/dev/null || echo "ai-email-routing")

# Create a simple test prompt
cat > routing-prompt.json <<'EOF'
{
  "pk": {"S": "CONFIG"},
  "sk": {"S": "routing_prompt"},
  "prompt": {"S": "Analyze this email and add [TEST] tag.\n\nFrom: {sender}\nSubject: {subject}\nBody: {body}\n\nReturn JSON only:\n{\"route_to\": [\"your@gmail.com\"], \"tags\": [\"TEST\"], \"confidence\": 1.0, \"reasoning\": \"Test routing\"}"},
  "enabled": {"BOOL": true},
  "updated_at": {"S": "2025-01-15T12:00:00Z"}
}
EOF

# Upload to DynamoDB
aws dynamodb put-item --table-name "$TABLE_NAME" --item file://routing-prompt.json
```

### 4. Test AI Routing

Send a test email - Claude will analyze it and add the [TEST] tag to the subject.

For advanced routing rules, see [docs/bedrock.md](docs/bedrock.md).

## How It Works

### Standard Email Flow

1. Email arrives at SES (`any-address@yourdomain.org`)
2. SES stores raw email in S3 bucket (`yourdomain.org/{messageId}`)
3. SES triggers Lambda function
4. Lambda fetches email from S3
5. Lambda creates new email with original attached as `message/rfc822`
6. Lambda forwards via SES to your destination address

### AI-Powered Flow (when enabled)

Same as above, plus:

3. Lambda extracts email content (text/HTML)
4. Lambda fetches routing prompt from DynamoDB
5. Lambda sends content to Bedrock Claude for analysis
6. Claude returns routing decision (recipients, tags, confidence)
7. Lambda routes to AI-determined recipient(s) with subject tags
8. Falls back to default forwarding if AI fails

## Cost Breakdown

Estimated monthly costs for 1,000 emails:

| Service | Cost |
|---------|------|
| SES receiving | $0.10 (first 1,000 free) |
| SES sending | $0.10 |
| S3 storage | $0.02 |
| Lambda execution | $0.00 (free tier) |
| Route53 hosted zone | $0.50 |
| DynamoDB | $0.00 (free tier) |
| **Total (standard mode)** | **~$0.72/month** |
| Bedrock Claude (AI mode) | +$0.90 |
| **Total (AI mode)** | **~$1.62/month** |

For 10,000 emails/month, expect ~$7-16 depending on AI usage.

## Monitoring and Logs

### View Lambda Logs

```bash
# Follow logs in real-time
aws logs tail /aws/lambda/ai-email-forwarder --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/ai-email-forwarder \
  --filter-pattern "ERROR"
```

### View AI Routing Decisions

```bash
# See AI routing decisions
aws logs filter-log-events \
  --log-group-name /aws/lambda/ai-email-forwarder \
  --filter-pattern "AI routing decision"
```

### Check DynamoDB Routing Prompt

```bash
aws dynamodb get-item \
  --table-name ai-email-routing \
  --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}' \
  --query 'Item.prompt.S' \
  --output text
```

## Troubleshooting

### No Emails Received

1. Check MX record points to SES:
   ```bash
   dig MX example.org
   # Should show: 10 inbound-smtp.us-east-1.amazonaws.com
   ```

2. Verify domain is verified in SES:
   ```bash
   aws ses get-identity-verification-attributes --identities example.org
   ```

3. Check Lambda logs for errors:
   ```bash
   aws logs tail /aws/lambda/ai-email-forwarder --follow
   ```

### AI Routing Not Working

1. Verify AI routing is enabled:
   ```bash
   terraform output | grep ai_routing
   ```

2. Check Bedrock model access:
   ```bash
   aws bedrock list-foundation-models --region us-east-1 | grep claude-sonnet-4-5
   ```

3. Verify routing prompt exists in DynamoDB:
   ```bash
   aws dynamodb get-item \
     --table-name ai-email-routing \
     --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}'
   ```

For detailed Bedrock troubleshooting, see [docs/bedrock.md](docs/bedrock.md).

### Multiple Domains Issues

1. **Previous domain stopped working**: Check that the SES receipt rule set `ses-catchall-forwarder-rules` is active:
   ```bash
   aws ses describe-active-receipt-rule-set
   ```

2. **Rule conflicts**: Ensure each domain uses a unique `project_name` in terraform.tfvars

3. **Wrong bucket**: Verify the Lambda `S3_PREFIX` environment variable matches the domain name

## Configuration Files

- `main.tf` - Main Terraform infrastructure configuration
- `variables.tf` - Input variables with defaults
- `outputs.tf` - Outputs for DNS and verification
- `lambda.py` - Python Lambda function for email forwarding
- `terraform.tfvars` - Your configuration (not in git)
- `CLAUDE.md` - Developer documentation for AI assistance
- `docs/bedrock.md` - Detailed Bedrock configuration and troubleshooting

## Advanced Configuration

### Disable Email Deletion

By default, emails are deleted from S3 after 30 days. To keep emails indefinitely:

1. Comment out the lifecycle rule in [main.tf:306-314](main.tf#L306-L314)
2. Run `terraform apply`

### Enable Verbose Logging

For detailed debugging information:

```bash
aws lambda update-function-configuration \
  --function-name ai-email-forwarder \
  --environment "Variables={VERBOSE_LOGGING=true,...}"
```

### Change Bedrock Model

To use a faster/cheaper model like Claude Haiku:

```hcl
# terraform.tfvars
bedrock_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
```

See [docs/bedrock.md](docs/bedrock.md) for model comparison.

## Security

This project follows AWS security best practices:

- S3 bucket blocks all public access
- IAM roles use least privilege permissions
- CloudWatch logs encrypted at rest (30-day retention)
- DynamoDB encryption at rest enabled
- SES enforces TLS for email transmission
- Lambda uses VPC endpoints (optional, not configured by default)

## Uninstalling

To remove all resources:

```bash
# Destroy infrastructure
terraform destroy

# Clean up local files
rm -rf .terraform terraform.tfstate* lambda.zip
```

Note: S3 bucket must be empty before destruction. Set `force_destroy = true` in main.tf to automatically empty bucket.

## Contributing

Contributions welcome! This project follows:
- Black for Python formatting
- Pylint for linting
- Terraform fmt for HCL formatting

```bash
# Format and lint
black lambda.py && pylint lambda.py
terraform fmt
```

## License

This project is provided as-is for educational and production use.

## Author

Simon Cornelius P. Umacob <f8cuek187@mozmail.com>
