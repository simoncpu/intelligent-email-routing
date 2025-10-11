# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A Terraform-deployed AWS infrastructure that creates an intelligent catch-all email forwarder with optional AI-powered routing:
- Receives emails sent to `*@yourdomain.org` via Amazon SES
- Stores raw emails in S3 for archival
- Forwards emails to designated addresses using a Python 3.13 Lambda function
- Preserves DMARC/SPF compliance by attaching original message as `message/rfc822`
- **AI-Powered Routing (Optional)**: Uses AWS Bedrock Claude to intelligently classify and route emails based on content analysis
- **Multi-Domain Support**: Adds new domains to existing SES receipt rule set (ses-catchall-forwarder-rules) to support multiple domains in the same AWS account and region

## Architecture

### Standard Email Forwarding Pipeline
1. **SES Receipt Rule** - receives inbound emails for the domain
2. **S3 Action** - stores raw email with prefix `inbound/{messageId}`
3. **Lambda Action** - `lambda.py:handler` processes the stored email
4. **SES SendRawEmail** - forwards email with original attached

### AI-Powered Routing Pipeline (when enabled)
1. **SES Receipt Rule** - receives inbound emails for the domain
2. **S3 Action** - stores raw email with prefix `inbound/{messageId}`
3. **Lambda Action** - enhanced handler with AI routing:
   - Fetches routing prompt from DynamoDB
   - Sends email content to Bedrock Claude for analysis
   - Routes to appropriate recipient(s) based on AI decision
   - Falls back to default forwarding if AI fails
4. **SES SendRawEmail** - forwards to AI-determined recipient(s)

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

# View Lambda logs (replace with actual function name)
aws logs tail /aws/lambda/ses-catchall-forwarder-forwarder --follow

# Test email forwarding
# Send email to any-address@yourdomain.org and check forwarded destination
```

## Key Files

- `main.tf` - Primary Terraform configuration defining AWS resources (SES, S3, Lambda, DynamoDB, IAM)
- `lambda.py` - Python 3.13 Lambda function that handles email forwarding with optional AI routing
- `variables.tf` - Terraform input variables with defaults including AI routing settings
- `outputs.tf` - DNS configuration values needed after deployment
- `terraform.tfvars` - Your configuration (domain, forward email, region, AI settings)
- `email-copilot.md` - Detailed documentation for AI-powered routing implementation

## Critical Configuration

### terraform.tfvars Requirements
```hcl
# Core Configuration
domain_name      = "yourdomain.org"        # Domain to receive emails
forward_to_email = "your@gmail.com"        # Default destination for forwarded emails
region           = "us-east-1"             # SES receiving region
dmarc_rua_email  = "re+xxx@dmarc.postmarkapp.com"  # Postmark DMARC report email

# AI Routing Configuration (Optional)
ai_routing_enabled     = false                                        # Enable AI-powered routing
bedrock_model_id       = "anthropic.claude-sonnet-4-5-20250929-v1:0" # Bedrock model for analysis (Claude Sonnet 4.5)
routing_fallback_email = ""                                           # Fallback if AI fails (uses forward_to_email if empty)
```

### Lambda Environment Variables (auto-configured)
- `S3_BUCKET` - Bucket storing raw emails
- `FORWARD_TO` - Default destination email address
- `FROM_ADDRESS` - Sender address for forwarded emails (`forwarder@yourdomain.org`)
- `VERBOSE_LOGGING` - Set to "true" for detailed logs
- `AI_ROUTING_ENABLED` - Enable/disable AI routing (from terraform variable)
- `ROUTING_TABLE` - DynamoDB table name for routing configuration
- `BEDROCK_MODEL_ID` - Bedrock model ID for email analysis

## DNS Requirements

After `terraform apply`, configure these DNS records at your domain registrar:

1. **MX Record**: `10 inbound-smtp.{region}.amazonaws.com`
2. **TXT Record**: `_amazonses.{domain}` with verification token from terraform output
3. **CNAME Records**: 3 DKIM tokens from terraform output → `*.dkim.amazonses.com`
4. **SPF Record**: `v=spf1 include:amazonses.com -all`
5. **DMARC Record**: Automatically configured using `dmarc_rua_email` from terraform.tfvars

### DMARC Report Analysis

To set up DMARC reporting with Postmark's free service:
1. Create a free account at https://dmarc.postmarkapp.com/
2. Copy the generated email address (format: `re+xxxxxxxxx@dmarc.postmarkapp.com`)
3. Add it to your `terraform.tfvars` as `dmarc_rua_email`
4. Run `terraform apply` to update the DMARC DNS record
5. Postmark will parse XML reports into readable weekly summaries with authentication statistics and potential issues

## Lambda Function Details

### Standard Mode
The `lambda.py:handler` function:
- Fetches raw email from S3 using SES messageId
- Parses original email for From/Subject headers
- Creates new email with original attached as `message/rfc822`
- Sets Reply-To to original sender for proper threading
- Uses `ses.send_raw_email()` for DMARC compliance

### AI-Powered Mode (when enabled)
Enhanced `lambda.py:handler` function:
- Performs all standard mode operations, plus:
- Extracts email content (text/HTML) for analysis
- Fetches routing prompt from DynamoDB table
- Sends content + prompt to Bedrock Claude model
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
- **Domain not verified**: Check DNS propagation and SES domain verification status
- **No emails received**: Verify MX record points to correct SES endpoint for your region
- **Lambda errors**: Check CloudWatch logs at `/aws/lambda/{function-name}`
- **DKIM failures**: Ensure all 3 DKIM CNAME records are properly configured

### Multi-Domain Issues
- **Previous domain stopped working**: Check that the correct rule set (ses-catchall-forwarder-rules) is active
- **Rule conflicts**: Ensure each domain has a unique rule name (project_name should differ per domain)
- **Wrong bucket/Lambda**: Verify S3_PREFIX environment variable matches domain name

### AI Routing Issues
- **AI routing not working**: Verify `ai_routing_enabled` is true in terraform.tfvars
- **Routing to wrong destination**: Check DynamoDB routing prompt configuration
- **Bedrock access denied**: Ensure Lambda IAM role has bedrock:InvokeModel permission
- **High latency**: Consider using Claude Haiku model for faster response times
- **Fallback always triggered**: Check Bedrock model availability in your region
- **Missing routing prompt**: Ensure DynamoDB table has routing_prompt entry

## Documentation Style Requirements

- NO emojis in any documentation files
- Use only ASCII characters (avoid em dash, en dash, curly quotes, etc.)
- Replace em dash (—) with regular hyphen (-) or "to"
- Replace en dash (–) with regular hyphen (-)
- Use straight quotes (") instead of curly quotes ("")
- Keep all text in standard ASCII range for maximum compatibility

## AI Routing Implementation Notes

When implementing AI-powered email routing:
1. **Start with AI disabled** - Deploy infrastructure with `ai_routing_enabled = false` first
2. **Test standard forwarding** - Ensure basic email forwarding works before enabling AI
3. **Configure DynamoDB prompt** - Add routing rules to DynamoDB before enabling AI
4. **Enable gradually** - Start with test emails before production traffic
5. **Monitor costs** - Track Bedrock usage to ensure costs remain reasonable
6. **Implement graceful fallback** - Always forward to default address if AI fails

For detailed implementation guide, see `email-copilot.md`

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
DO NOT create mocks unless it's specifically for testing. Use real data. Fail otherwise.
DO NOT overengineer. Prefer simple and easy to maintain solutions. Complex solutions can be presented as an option.