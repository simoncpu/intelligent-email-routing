# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A Terraform-deployed AWS infrastructure that creates an intelligent catch-all email forwarder with optional AI-powered routing:
- Receives emails sent to `*@yourdomain.org` via Amazon SES
- Stores raw emails in S3 for archival (30-day retention by default)
- Forwards emails to designated addresses using a Python 3.13 Lambda function
- Preserves DMARC/SPF compliance by forwarding original content inline with forwarding context
- Attaches original email as `message/rfc822` for reference
- **AI-Powered Routing (Optional)**: Uses AWS Bedrock Claude Sonnet 4.5 to intelligently classify and route emails based on content analysis
- **MCP Server (Optional)**: Conversational prompt management through Claude Code via Model Context Protocol (JSON-RPC 2.0, MCP 2025-03-26)
- **Multi-Domain Support**: Uses shared SES receipt rule set (ses-catchall-forwarder-rules) to support multiple domains in the same AWS account and region

## Architecture

### Standard Email Forwarding Pipeline
1. **SES Receipt Rule** - receives inbound emails for the domain
2. **S3 Action** - stores raw email with prefix `{domain_name}/{messageId}`
3. **Lambda Action** - `lambda.py:handler` processes the stored email
4. **SES SendRawEmail** - forwards email with original content inline and attached

### AI-Powered Routing Pipeline (when enabled)
1. **SES Receipt Rule** - receives inbound emails for the domain
2. **S3 Action** - stores raw email with prefix `{domain_name}/{messageId}`
3. **Lambda Action** - enhanced handler with AI routing:
   - Extracts email content (text and HTML)
   - Fetches routing prompt from DynamoDB
   - Sends email content to Bedrock Claude for analysis
   - Routes to appropriate recipient(s) based on AI decision
   - Falls back to default forwarding if AI fails
4. **SES SendRawEmail** - forwards to AI-determined recipient(s) with tags

## Core Commands

### Deployment
```bash
# Initialize Terraform (first time only)
terraform init

# Preview changes
terraform plan

# Deploy infrastructure
terraform apply

# Destroy infrastructure
terraform destroy
```

### Configuration
```bash
# Copy and edit configuration template
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your domain and email settings
```

### Testing and Verification
```bash
# Check Terraform outputs for DNS configuration
terraform output

# View Lambda logs (replace with actual function name from outputs)
aws logs tail /aws/lambda/{project-name}-forwarder --follow

# Test email forwarding
# Send email to any-address@yourdomain.org and check forwarded destination
```

## Key Files

- `main.tf` - Primary Terraform configuration defining AWS resources (SES, S3, Lambda, DynamoDB, IAM, MCP server)
- `lambda.py` - Python 3.13 Lambda function that handles email forwarding with optional AI routing
- `mcp_lambda.py` - Python 3.13 Lambda function for MCP server (prompt management)
- `variables.tf` - Terraform input variables with defaults including AI routing settings
- `outputs.tf` - DNS configuration values and resource identifiers
- `terraform.tfvars` - Your configuration (domain, forward email, region, AI settings) - not in git
- `terraform.tfvars.example` - Template for configuration
- `email-copilot.md` - Planning document for AI-powered routing implementation
- `docs/bedrock.md` - Detailed Bedrock configuration, troubleshooting, and cost optimization
- `docs/mcp-server.md` - MCP server setup, API key management, and usage guide
- `.env` - MCP API key for initial setup (not in git)

## Critical Configuration

### terraform.tfvars Requirements
```hcl
# Core Configuration (required)
domain_name      = "yourdomain.org"        # Domain to receive emails
forward_to_email = "your@gmail.com"        # Default destination for forwarded emails
region           = "us-east-1"             # SES receiving region
s3_bucket        = "my-email-bucket"       # S3 bucket name for storing emails
dmarc_rua_email  = "re+xxx@dmarc.postmarkapp.com"  # Postmark DMARC report email

# AI Routing Configuration (optional)
ai_routing_enabled     = false                                       # Enable AI-powered routing
bedrock_model_id       = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"  # Bedrock inference profile (Claude Sonnet 4.5)
routing_fallback_email = ""                                          # Fallback if AI fails (uses forward_to_email if empty)
```

**Note**: `bedrock_model_id` uses cross-region inference profile format, not direct model ID. See [docs/bedrock.md](docs/bedrock.md) for details.

### Lambda Environment Variables (auto-configured)
- `S3_BUCKET` - Bucket storing raw emails
- `S3_PREFIX` - S3 prefix based on domain name (`{domain_name}/`)
- `FORWARD_TO` - Default destination email address
- `FROM_ADDRESS` - Sender address for forwarded emails (`forwarder@yourdomain.org`)
- `VERBOSE_LOGGING` - Set to "true" for detailed logs
- `AI_ROUTING_ENABLED` - Enable/disable AI routing (from terraform variable)
- `ROUTING_TABLE` - DynamoDB table name for routing configuration
- `BEDROCK_MODEL_ID` - Bedrock inference profile ID for email analysis

## DNS Requirements

After `terraform apply`, DNS records are automatically configured in Route53 (uses existing hosted zone):

1. **MX Record**: `10 inbound-smtp.{region}.amazonaws.com` - for receiving emails
2. **TXT Record**: `_amazonses.{domain}` with verification token - for SES domain verification
3. **CNAME Records**: 3 DKIM tokens from SES → `*.dkim.amazonses.com` - for email authentication
4. **SPF Record**: `v=spf1 include:amazonses.com -all` - for sender authentication
5. **SPF Record (MAIL FROM)**: `v=spf1 include:amazonses.com -all` on `forwarder.{domain}`
6. **DMARC Record**: Configured using `dmarc_rua_email` from terraform.tfvars
7. **MX Record (MAIL FROM)**: `10 feedback-smtp.{region}.amazonses.com` on `forwarder.{domain}` - for bounce handling

### DMARC Report Analysis

To set up DMARC reporting with Postmark's free service:
1. Create a free account at https://dmarc.postmarkapp.com/
2. Copy the generated email address (format: `re+xxxxxxxxx@dmarc.postmarkapp.com`)
3. Add it to your `terraform.tfvars` as `dmarc_rua_email`
4. Run `terraform apply` to update the DMARC DNS record
5. Postmark will parse XML reports into readable weekly summaries with authentication statistics and potential issues

## Lambda Function Details

### Standard Mode
The `lambda.py:handler` function ([lambda.py:222-348](lambda.py#L222-L348)):
- Fetches raw email from S3 using SES messageId
- Parses original email for From/Subject/Date headers
- Extracts text and HTML content
- Creates forwarding context (From/To/Date header shown visually)
- Creates new email with original content inline
- Attaches original email as `message/rfc822` for reference
- Sets Reply-To to original sender for proper threading
- Uses `ses.send_raw_email()` for DMARC compliance

### AI-Powered Mode (when enabled)
Enhanced `lambda.py:handler` function:
- Performs all standard mode operations, plus:
- Extracts email content for analysis ([lambda.py:32-67](lambda.py#L32-L67))
- Fetches routing prompt from DynamoDB ([lambda.py:93-133](lambda.py#L93-L133))
- Sends content + prompt to Bedrock Claude model ([lambda.py:136-220](lambda.py#L136-L220))
- Parses AI response for routing destinations and tags
- Routes email to AI-determined recipient(s) with subject tags
- Falls back to default forwarding if AI analysis fails
- Logs routing decisions for monitoring and debugging

## Development Setup

### Install development dependencies
```bash
pip install -r requirements-dev.txt
```

### Code formatting and linting
```bash
# Format code with Black (auto-runs on save in VSCode)
black lambda.py

# Check code quality with Pylint
pylint lambda.py

# Check style with Flake8
flake8 lambda.py

# Sort imports
isort lambda.py

# Run all linting checks
black lambda.py && isort lambda.py && pylint lambda.py && flake8 lambda.py
```

## Troubleshooting

### Standard Issues
- **Domain not verified**: Check DNS propagation and SES domain verification status with `aws ses get-identity-verification-attributes`
- **No emails received**: Verify MX record points to correct SES endpoint for your region with `dig MX yourdomain.org`
- **Lambda errors**: Check CloudWatch logs at `/aws/lambda/{project-name}-forwarder`
- **DKIM failures**: Ensure all 3 DKIM CNAME records are properly configured in Route53

### Multi-Domain Issues
- **Previous domain stopped working**: Check that the correct rule set (ses-catchall-forwarder-rules) is active with `aws ses describe-active-receipt-rule-set`
- **Rule conflicts**: Ensure each domain has a unique rule name (project_name should differ per domain)
- **Wrong bucket/Lambda**: Verify S3_PREFIX environment variable matches domain name (`{domain_name}/`)

### AI Routing Issues

For detailed AI routing troubleshooting, see [docs/bedrock.md](docs/bedrock.md).

Common issues:
- **AI routing not working**: Verify `ai_routing_enabled` is true in terraform.tfvars
- **Routing to wrong destination**: Check DynamoDB routing prompt configuration
- **Bedrock access denied**: Ensure Lambda IAM role has bedrock:InvokeModel permission for both inference profile and foundation model
- **Missing routing prompt**: Ensure DynamoDB table has item with pk="CONFIG", sk="routing_prompt"

## Documentation Style Requirements

- NO emojis in any documentation files
- Use only ASCII characters (avoid em dash, en dash, curly quotes, etc.)
- Replace em dash (—) with regular hyphen (-) or "to"
- Replace en dash (–) with regular hyphen (-)
- Use straight quotes (") instead of curly quotes ("")
- Keep all text in standard ASCII range for maximum compatibility

## Security and PII Requirements

**CRITICAL**: Never document or commit the following sensitive information to git:

### Prohibited Information
- **API Keys**: Never include real MCP API keys, AWS access keys, or any authentication tokens in tracked files
- **Personal Email Addresses**: Use placeholders like `user@example.com` or `example@gmail.com` instead of real addresses
- **Personal Names**: Avoid full names in documentation (git commit history is acceptable)
- **Domain Names**: Use `yourdomain.org` or `example.com` instead of real domains
- **AWS Resource IDs**: Never include Lambda function URLs, S3 bucket names, or other resource identifiers that could expose infrastructure
- **Credentials**: No passwords, secrets, or private keys in any tracked files

### Safe Practices
- Always use example placeholders in documentation
- Keep sensitive data in `.env` and `terraform.tfvars` (both are gitignored)
- Use `terraform.tfvars.example` for templates with placeholder values only
- When documenting API keys, use fake examples like `your-api-key-here` or `xxxxxxxx`
- Review documentation files before committing to ensure no PII is present
- The acceptable test email `f8cuek187@mozmail.com` may be used in examples

### Files That Should NEVER Contain Real Values
- README.md
- CLAUDE.md
- docs/*.md
- *.example files
- Any file tracked in git (except .gitignore itself)

## AI Routing Implementation Notes

When implementing or modifying AI-powered email routing:
1. **Start with AI disabled** - Deploy infrastructure with `ai_routing_enabled = false` first
2. **Test standard forwarding** - Ensure basic email forwarding works before enabling AI
3. **Configure DynamoDB prompt** - Add routing rules to DynamoDB before enabling AI
4. **Enable gradually** - Start with test emails before production traffic
5. **Monitor costs** - Track Bedrock usage to ensure costs remain reasonable
6. **Implement graceful fallback** - Always forward to default address if AI fails

For detailed implementation guide, model selection, cost optimization, and troubleshooting, see [docs/bedrock.md](docs/bedrock.md).

## Multi-Domain Setup Notes

When setting up multiple domains in the same AWS account:
1. **Use different project_name** - Each domain needs unique resource names
2. **Use same region** - SES has only one active rule set per region
3. **Use different S3 bucket** - Each domain should have its own bucket
4. **Keep separate Terraform state** - Use different directories for each domain
5. **Shared rule set** - All domains use `ses-catchall-forwarder-rules` receipt rule set
6. **Manual rule set activation** - If rule set becomes inactive, activate it manually:
   ```bash
   aws ses set-active-receipt-rule-set --rule-set-name ses-catchall-forwarder-rules
   ```

## Security Notes

- S3 bucket has public access blocked by default
- IAM roles use least privilege permissions
- CloudWatch logs retained for 30 days (configurable in [main.tf:214-217](main.tf#L214-L217))
- DynamoDB has encryption at rest enabled
- SES enforces TLS for email transmission
- Lambda timeout set to 30 seconds (configurable in [main.tf:236](main.tf#L236))
- S3 lifecycle deletes emails after 30 days (configurable in [main.tf:306-314](main.tf#L306-L314))

## Cost Optimization

### Standard Mode (no AI)
- SES receiving: ~$0.10 per 1,000 emails
- SES sending: ~$0.10 per 1,000 emails
- S3 storage: minimal (30-day retention)
- Lambda: free tier covers most usage
- Route53 hosted zone: ~$0.50/month

### AI Mode
- Add ~$0.90 per 1,000 emails for Bedrock Claude Sonnet 4.5
- DynamoDB pay-per-request: minimal cost
- See [docs/bedrock.md](docs/bedrock.md) for detailed cost breakdown and optimization strategies

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
DO NOT create mocks unless it's specifically for testing. Use real data. Fail otherwise.
DO NOT overengineer. Prefer simple and easy to maintain solutions. Complex solutions can be presented as an option.
