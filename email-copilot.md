# Email Copilot - AI-Powered Email Routing System

## Overview

Transform the existing catch-all email forwarder into an intelligent routing system that uses AWS Bedrock AI to automatically classify, tag, and route emails based on their content. The system reads routing instructions from DynamoDB and uses Claude to analyze each incoming email and determine the appropriate destination(s).

## Architecture

```
Email Flow:
1. Email arrives at *@yourdomain.org (SES)
2. Stored in S3 bucket (existing)
3. Lambda triggered (enhanced with AI)
4. Lambda fetches routing prompt from DynamoDB
5. Lambda sends email content + prompt to Bedrock Claude
6. Claude analyzes and returns routing decision
7. Lambda forwards email to appropriate recipient(s) with tags
8. Fallback to default forwarding if AI fails
```

## Use Cases

### Core Routing Examples
- **Customer Support**: Route to support@example.com
- **Account Issues**: Prepend [ACCOUNT] and route to support@example.com
- **Sales Inquiries**: Route to sales@example.com
- **Job Applications**: Route to jobs@example.com
- **Technical Issues**: Route to tech-support@example.com
- **Billing/Invoices**: Route to accounting@example.com
- **Partnership Requests**: Route to bizdev@example.com

### Advanced Classification
- **Priority Tagging**: Add [URGENT], [HIGH], [NORMAL] based on content urgency
- **Language Detection**: Route to language-specific teams (support-es@, support-fr@)
- **Sentiment Analysis**: Flag angry/frustrated customers with [ESCALATION] tag
- **Lead Scoring**: Score and route high-value prospects to senior-sales@
- **Compliance Detection**: Route GDPR/legal notices to legal@example.com
- **Security Alerts**: Detect phishing attempts, route to security@example.com
- **Auto-Response**: Generate draft responses for common queries
- **Newsletter Filter**: Auto-detect and filter marketing emails

## Implementation Components

### 1. DynamoDB Table Structure

```
Table: ses-catchall-forwarder-routing
Composite Key Schema:
  - Partition Key (pk): "CONFIG"
  - Sort Key (sk): "routing_prompt"

Attributes:
  - pk: "CONFIG" (partition key)
  - sk: "routing_prompt" (sort key)
  - prompt: Text containing routing instructions
  - enabled: Boolean to enable/disable AI routing
  - model_id: Bedrock model to use (default: "anthropic.claude-sonnet-4-5-20250929-v1:0")
  - temperature: Float for response consistency (default: 0.1)
  - max_tokens: Integer for response length (default: 500)
  - updated_at: ISO 8601 timestamp
  - fallback_email: Default destination if AI fails
```

### 2. Routing Prompt Template

**Default Initial Prompt (stored in DynamoDB):**
```
Prepend [TEST] to e-mail subjects for all incoming email.
```

**Example Advanced Routing Prompt:**
```
You are an email routing assistant. Analyze the following email and determine where it should be forwarded based on these rules:

ROUTING RULES:
- Customer support inquiries -> support@example.com
- Account-related issues -> support@example.com with [ACCOUNT] tag
- Sales/purchasing inquiries -> sales@example.com
- Job applications -> jobs@example.com with [RECRUITING] tag
- Technical issues -> tech-support@example.com with priority level
- Invoices/billing -> accounting@example.com with [INVOICE] tag
- Partnership/business development -> bizdev@example.com
- Legal/compliance (GDPR, etc.) -> legal@example.com with [COMPLIANCE] tag
- Security concerns/phishing -> security@example.com with [SECURITY] tag
- Marketing/newsletters -> marketing-archive@example.com

PRIORITY LEVELS:
- Urgent keywords (urgent, critical, emergency) -> Add [URGENT]
- Frustrated/angry tone -> Add [ESCALATION]
- VIP domains (@fortune500.com) -> Add [VIP]

EMAIL CONTENT:
From: {sender}
Subject: {subject}
Body: {body}

RESPONSE FORMAT:
Return JSON only:
{
  "route_to": ["email@example.com"],
  "tags": ["TAG1", "TAG2"],
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}
```

### 3. Lambda Function Enhancements

#### New Dependencies
```python
import json
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.client('dynamodb')
bedrock = boto3.client('bedrock-runtime')
```

#### AI Routing Logic
```python
def get_ai_routing_decision(email_content):
    """
    Use Bedrock Claude to determine email routing.
    Returns: dict with route_to, tags, confidence
    """
    # Fetch prompt from DynamoDB
    # Prepare email content for analysis
    # Call Bedrock Claude
    # Parse AI response
    # Return routing decision or None on failure
```

#### Enhanced Handler
```python
def handler(event, context):
    # Existing email processing...

    # New: AI routing
    if AI_ROUTING_ENABLED:
        routing_decision = get_ai_routing_decision({
            'sender': orig_from,
            'subject': subject,
            'body': text_content
        })

        if routing_decision:
            # Apply AI routing
            forward_to_addresses = routing_decision['route_to']
            subject_tags = ' '.join(f'[{tag}]' for tag in routing_decision['tags'])
            enhanced_subject = f"{subject_tags} {subject}" if subject_tags else subject
        else:
            # Fallback to default
            forward_to_addresses = [FORWARD_TO]
            enhanced_subject = subject

    # Continue with forwarding...
```

### 4. Terraform Infrastructure Updates

#### DynamoDB Table
```hcl
resource "aws_dynamodb_table" "routing" {
  name         = "${var.project_name}-routing"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  tags = {
    Name        = "${var.project_name}-routing"
    Purpose     = "AI email routing and general storage"
    ManagedBy   = "Terraform"
  }
}
```

**Composite Key Pattern**: This table uses a hierarchical key design:
- **Partition Key (pk)**: Entity type (e.g., "CONFIG", "EMAIL", "USER")
- **Sort Key (sk)**: Entity identifier (e.g., "routing_prompt", "2025-01-15#msg123")

**Example Data Structure**:
```
pk="CONFIG"     sk="routing_prompt"     -> AI routing prompt
pk="CONFIG"     sk="settings"           -> Application settings
pk="EMAIL"      sk="2025-01-15#msg123"  -> Email record
pk="USER"       sk="user@example.com"   -> User preferences
```

#### IAM Permissions
```hcl
# Add to existing Lambda IAM policy
{
  Effect = "Allow",
  Action = [
    "dynamodb:GetItem",
    "dynamodb:Query"
  ],
  Resource = aws_dynamodb_table.routing.arn
},
{
  Effect = "Allow",
  Action = [
    "bedrock:InvokeModel"
  ],
  Resource = "arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"
}
```

#### Lambda Environment Variables
```hcl
environment {
  variables = {
    # Existing variables...
    ROUTING_TABLE     = aws_dynamodb_table.routing.name
    AI_ROUTING_ENABLED = var.ai_routing_enabled
    BEDROCK_MODEL_ID  = var.bedrock_model_id
  }
}
```

### 5. New Terraform Variables

```hcl
variable "ai_routing_enabled" {
  type        = bool
  default     = false
  description = "Enable AI-powered email routing"
}

variable "bedrock_model_id" {
  type        = string
  default     = "anthropic.claude-sonnet-4-5-20250929-v1:0"
  description = "AWS Bedrock model ID for email analysis (Claude Sonnet 4.5)"
}

variable "routing_fallback_email" {
  type        = string
  default     = ""
  description = "Fallback email if AI routing fails (defaults to forward_to_email)"
}
```

## Monitoring and Logging

### CloudWatch Metrics
- AI routing success/failure rate
- Average processing time
- Confidence scores distribution
- Routing destinations frequency

### Log Examples
```json
{
  "level": "INFO",
  "message": "AI routing decision",
  "email_id": "xxx",
  "from": "customer@example.com",
  "routing": {
    "destinations": ["support@example.com"],
    "tags": ["URGENT", "ACCOUNT"],
    "confidence": 0.92,
    "reasoning": "Account access issue with urgent language"
  }
}
```

## Testing Strategy

### Test Cases
1. **Customer Support**: "I can't access my account"
2. **Sales Inquiry**: "I'd like to purchase your enterprise plan"
3. **Job Application**: "I'm applying for the Software Engineer position"
4. **Invoice**: "Please find attached invoice #12345"
5. **Security Alert**: "Suspicious login attempt detected"
6. **Multiple Intents**: Complex emails requiring multiple routes
7. **Edge Cases**: Ambiguous content, non-English emails

### Testing Commands
```bash
# Send test email
echo "Test email body" | mail -s "Test Subject" test@yourdomain.org

# Monitor Lambda logs
aws logs tail /aws/lambda/ses-catchall-forwarder-forwarder --follow

# Check DynamoDB prompt
aws dynamodb get-item --table-name ses-catchall-forwarder-routing --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}'

# Update routing prompt
aws dynamodb put-item --table-name ses-catchall-forwarder-routing --item file://routing-prompt.json
```

## Rollout Plan

### Phase 1: Infrastructure Setup
1. Deploy DynamoDB table
2. Add Bedrock permissions
3. Deploy updated Lambda with AI routing disabled

### Phase 2: Testing
1. Enable AI routing for test domain
2. Send test emails covering all use cases
3. Monitor and tune routing prompt
4. Verify fallback behavior

### Phase 3: Production
1. Enable AI routing in production
2. Monitor metrics and logs
3. Iterate on routing rules based on real traffic
4. Add new routing rules as needed

## Cost Considerations

### Estimated Monthly Costs (1000 emails/month)
- DynamoDB: ~$0.25 (pay-per-request)
- Bedrock Claude Sonnet 4.5: ~$0.50-1.00 (1000 requests @ ~500 tokens each)
- Additional Lambda execution: ~$0.10
- Total additional cost: ~$0.85-1.35/month

### Cost Optimization
- Claude Sonnet 4.5 offers excellent accuracy for email routing
- Cache routing decisions for similar emails
- Batch process during off-peak hours
- Set confidence threshold to reduce AI calls
- For high-volume use cases, consider Claude Haiku (faster, cheaper)

## Security Considerations

### Data Privacy
- Email content sent to Bedrock for analysis
- No persistent storage of email content in AI service
- Use VPC endpoints for Bedrock if required
- Implement data masking for sensitive information

### Access Control
- Lambda role with minimal permissions
- DynamoDB encryption at rest
- Separate roles for prompt management
- Audit trail for routing decisions

## MCP Server for Interactive Prompt Management

### Purpose

Expose a Model Context Protocol (MCP) server that allows AI assistants (like Claude Desktop) to help users interactively create and refine email routing prompts through natural conversation. The MCP server bridges conversational AI with DynamoDB routing configuration.

### Key Requirements

**Goal**: Enable users to work conversationally with AI to build and refine routing prompts without manually editing DynamoDB or redeploying infrastructure.

**Core Capabilities**:
- Get current routing prompt from DynamoDB
- Update routing prompt through conversation
- View prompt change history
- Validate prompt syntax before applying

### Architecture Overview

```
Claude Desktop (MCP Client) <-> Lambda Function URL <-> MCP Lambda <-> DynamoDB
```

**Key Decisions**:
- Use Lambda Function URL (not API Gateway) for simplicity and cost savings
- Use open auth with API key validation (not IAM auth) for easier client setup
- Store API keys as SHA256 hashes in existing DynamoDB routing table
- Leverage composite key pattern: pk="API_KEY", sk="<hash>"

### Infrastructure Components

**Lambda Function**:
- Python 3.13 runtime with awslabs.mcp-lambda-handler library
- Function URL with CORS enabled
- 30-second timeout
- Environment variables: ROUTING_TABLE

**API Key Storage in DynamoDB**:
- Uses existing routing table with composite key pattern
- pk="API_KEY", sk=SHA256(api_key)
- Attributes: key_name, created_at, expires_at, is_active, permissions, last_used_at
- Keys can be created, revoked, and have expiration dates

**IAM Permissions**:
- DynamoDB: GetItem, PutItem, UpdateItem, Query on routing table
- CloudWatch Logs: CreateLogStream, PutLogEvents

**Outputs**:
- Function URL for MCP client configuration

### MCP Tools

Expose these tools for prompt management:
1. get_routing_prompt() - Fetch current prompt from DynamoDB
2. update_routing_prompt(prompt) - Update prompt in DynamoDB
3. get_prompt_history() - View previous prompt versions
4. validate_prompt_syntax(prompt) - Check if prompt is valid

### Conversation Flow Example

User asks Claude Desktop to help set up email routing. Claude uses MCP tools to:
1. Get current prompt configuration
2. Ask user about their routing needs
3. Build prompt iteratively through conversation
4. Validate syntax before applying
5. Update production prompt when user approves

### API Key Management

**Create Key**: Generate random key, hash with SHA256, store in DynamoDB with permissions
**Revoke Key**: Update is_active flag to false
**Permissions**: Each key has list of allowed MCP tools

### Cost Considerations

Lambda Function URL approach saves 90% vs API Gateway:
- Lambda Function URL: No charge
- Lambda invocations: ~$0.02/month (100 updates)
- DynamoDB: ~$0.01/month
- Total: ~$0.04/month vs ~$0.38/month with API Gateway

### Security

- API keys stored as irreversible SHA256 hashes
- HTTPS enforced by Lambda Function URL
- Per-key permissions and expiration dates
- All access logged in CloudWatch
- No AWS credentials needed by MCP clients

### Prompt Version History

Store prompt versions in DynamoDB for rollback:
- pk="HISTORY", sk="routing_prompt#<timestamp>"
- Enables tracking changes and reverting to previous versions

## Future Enhancements

### Advanced Features
1. **Multi-step Routing**: Chain multiple AI decisions
2. **Custom Actions**: Beyond forwarding (auto-reply, ticket creation)
3. **Learning System**: Improve routing based on feedback
4. **Template Responses**: AI-generated reply drafts
5. **Attachment Analysis**: Route based on attachment types
6. **Time-based Routing**: Different rules for business hours
7. **Escalation Paths**: Automatic escalation for unresolved issues
8. **Analytics Dashboard**: Visualize routing patterns

### MCP Server Enhancements
- Test prompts against sample emails before deploying
- A/B testing with multiple prompts
- Natural language prompt builder
- AI-powered prompt optimization suggestions
- Real-time routing analytics

### Integration Possibilities
- Slack/Teams notifications for urgent emails
- CRM integration for customer context
- Ticketing system integration
- Calendar integration for meeting requests
- Translation services for international emails