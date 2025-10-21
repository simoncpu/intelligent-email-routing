# Architecture Documentation

## How It Works

This document describes the technical implementation details of the intelligent email forwarding system.

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

## Implementation Files

### Terraform Infrastructure

- `main.tf` - Main Terraform infrastructure configuration
  - Defines SES receipt rules, S3 buckets, Lambda functions, DynamoDB tables
  - Configures IAM roles and policies
  - Sets up Route53 DNS records automatically
  - Creates MCP server with public Lambda URL

- `variables.tf` - Input variables with defaults
  - Domain configuration
  - AI routing settings
  - Bedrock model selection
  - Resource naming

- `outputs.tf` - Outputs for DNS and verification
  - DNS record values
  - Lambda function ARNs
  - MCP server URL
  - DynamoDB table names

### Lambda Functions

- `lambda.py` - Python 3.13 Lambda function for email forwarding
  - Handler function: `lambda.py:handler` (lines 222-348)
  - Email content extraction: `lambda.py:extract_email_content` (lines 32-67)
  - DynamoDB prompt fetching: `lambda.py:get_routing_prompt` (lines 93-133)
  - Bedrock AI routing: `lambda.py:get_ai_routing_decision` (lines 136-220)
  - Preserves DMARC/SPF compliance
  - Attaches original email as `message/rfc822`
  - Sets Reply-To for proper threading

- `mcp_lambda.py` - Python 3.13 Lambda function for MCP server
  - Implements JSON-RPC 2.0 protocol (MCP 2025-03-26)
  - Provides tools for prompt management
  - API key authentication via DynamoDB
  - Public Lambda URL with HTTPS endpoint

### Configuration

- `terraform.tfvars` - User configuration (not in git)
  - Domain settings
  - Email addresses
  - AI routing options
  - AWS region

- `terraform.tfvars.example` - Template for configuration

### Documentation

- `CLAUDE.md` - Developer documentation for AI assistance
  - Project structure
  - Development workflow
  - Security requirements
  - Multi-domain setup notes

- `docs/bedrock.md` - Detailed Bedrock configuration and troubleshooting
  - Model selection guide
  - Cost optimization strategies
  - Prompt engineering tips
  - Troubleshooting guide

- `docs/mcp-server.md` - MCP server setup and usage guide
  - API key management
  - Claude Code configuration
  - Security best practices
  - Troubleshooting

### Helper Scripts

- `scripts/create-api-key.sh` - Helper script to create MCP API keys
  - Generates secure random API keys
  - Stores hashed keys in DynamoDB
  - Saves plaintext key to `.env` for user

## AWS Resources Created

When you run `terraform apply`, these resources are created:

### DNS & Email (SES)
- Route53 records (MX, TXT, CNAME, DMARC) in existing hosted zone
- SES domain identity with DKIM verification
- SES receipt rule in shared rule set `ses-catchall-forwarder-rules`
- MAIL FROM domain configuration (`forwarder.{domain}`)

### Storage
- S3 bucket for raw email storage
  - Bucket name from `s3_bucket` variable
  - Prefix: `{domain_name}/`
  - Public access blocked
  - 30-day lifecycle policy (configurable)
  - Encryption at rest

### Compute
- Lambda function for email forwarding
  - Runtime: Python 3.13
  - Timeout: 30 seconds (configurable)
  - Memory: 256 MB (configurable)
  - Environment variables: S3_BUCKET, S3_PREFIX, FORWARD_TO, FROM_ADDRESS, AI_ROUTING_ENABLED, etc.

- Lambda function for MCP server (optional)
  - Runtime: Python 3.13
  - Public Lambda function URL
  - HTTPS only
  - No IAM authentication (uses API key in headers)

### Database
- DynamoDB table (when AI routing enabled)
  - Table name from `dynamodb_table` variable
  - Partition key: `pk` (string)
  - Sort key: `sk` (string)
  - Pay-per-request billing
  - Encryption at rest
  - Stores: routing prompts, prompt history, API keys

### IAM
- Lambda execution role with minimal permissions:
  - S3: GetObject (for fetching emails)
  - SES: SendRawEmail (for forwarding)
  - Bedrock: InvokeModel (for AI routing, if enabled)
  - DynamoDB: GetItem, PutItem, Query (for routing config, if enabled)
  - CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

### Monitoring
- CloudWatch log groups
  - `/aws/lambda/{project-name}-forwarder`
  - `/aws/lambda/{project-name}-mcp-server` (if MCP enabled)
  - 30-day retention (configurable)
  - Encryption at rest

## Multi-Domain Architecture

The system uses a shared SES receipt rule set approach to support multiple domains:

### Shared Resources (per AWS region)
- Receipt rule set: `ses-catchall-forwarder-rules`
  - Only one active rule set allowed per region
  - Contains receipt rules for all domains
  - Automatically created if it doesn't exist
  - Must be manually activated if it becomes inactive

### Per-Domain Resources
- Unique S3 bucket (different `s3_bucket` value)
- Unique Lambda function (different `project_name`)
- Unique DynamoDB table (different `dynamodb_table` value)
- Unique SES receipt rule (named `{project_name}-rule`)
- Unique Route53 records in respective hosted zones

### S3 Prefix Strategy
Each domain uses a unique S3 prefix to isolate emails:
- Domain 1: `domain1.com/{messageId}`
- Domain 2: `domain2.org/{messageId}`

Lambda function's `S3_PREFIX` environment variable ensures it only processes emails for its domain.

### Rule Set Activation
If the shared rule set becomes inactive:
```bash
aws ses set-active-receipt-rule-set --rule-set-name ses-catchall-forwarder-rules
```

## Security Architecture

### Email Security
- **DMARC/SPF/DKIM**: Fully compliant email authentication
- **TLS**: SES enforces TLS 1.2+ for all email transmission
- **Original email preservation**: Attached as `message/rfc822` to maintain integrity
- **MAIL FROM domain**: Uses subdomain (`forwarder.{domain}`) for proper bounce handling

### Storage Security
- **S3**:
  - Public access blocked via bucket policy
  - Encryption at rest (AES-256)
  - Bucket versioning disabled
  - Lifecycle policy for automatic deletion

- **DynamoDB**:
  - Encryption at rest enabled
  - Point-in-time recovery disabled (cost optimization)
  - API keys stored as SHA-256 hashes
  - Prompts versioned with timestamps

### Compute Security
- **Lambda**:
  - No VPC configuration (uses VPC endpoints if needed)
  - Minimal IAM permissions (least privilege)
  - Environment variables for configuration (no secrets)
  - Execution role scoped to specific resources

- **MCP Server**:
  - Public URL with API key authentication
  - API keys stored hashed in DynamoDB
  - HTTPS only (enforced by Lambda URL)
  - No IAM authentication (uses custom bearer token)

### IAM Security
- Separate execution roles per Lambda function
- Resource-based policies for S3/DynamoDB access
- No cross-account access
- CloudWatch Logs access only for own log groups

### Monitoring Security
- CloudWatch logs encrypted at rest
- 30-day retention (configurable)
- No PII in log messages (email content not logged)
- AI routing decisions logged (metadata only)

## Cost Considerations

### Per-Email Costs (Standard Mode)
- SES receiving: $0.10 per 1,000 emails
- SES sending: $0.10 per 1,000 emails
- Lambda invocations: Free tier covers most usage
- S3 storage: Minimal (30-day retention)

### Per-Email Costs (AI Mode)
- Add Bedrock Claude Sonnet 4.5: ~$0.90 per 1,000 emails
- DynamoDB reads: Negligible (pay-per-request)

### Monthly Fixed Costs
- Route53 hosted zone: $0.50/month per domain
- CloudWatch logs: Minimal (30-day retention)

### Optimization Strategies
See [bedrock.md](bedrock.md) for detailed cost optimization strategies:
- Model selection (Haiku vs Sonnet)
- Prompt length optimization
- Caching strategies
- Selective AI routing

## Performance Characteristics

### Latency
- Standard mode: ~500ms average (S3 fetch + SES send)
- AI mode: ~2-5 seconds (includes Bedrock API call)
- MCP server: ~200ms (DynamoDB read)

### Throughput
- SES receiving: Up to 1,000 emails/second (regional limit)
- Lambda concurrency: 1,000 concurrent executions (default limit)
- DynamoDB: Unlimited (pay-per-request mode)

### Reliability
- SES: 99.99% uptime SLA
- Lambda: Automatic retries on failure
- S3: 99.999999999% durability
- Fallback: AI failures default to standard forwarding
