# AWS Bedrock Configuration for AI Email Routing

This document contains Bedrock-specific configuration and troubleshooting information for the AI-powered email routing feature.

## Model Configuration

### Bedrock Inference Profile

The system uses AWS Bedrock cross-region inference profiles to ensure high availability and automatic failover:

- **Default Model**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- **Profile Type**: Cross-region inference profile
- **Primary Region**: Configured via `region` variable in terraform.tfvars
- **Failover**: Automatic to other regions if primary is unavailable

### Model Parameters

Default parameters used in Lambda (configured in [lambda.py:159-164](../lambda.py#L159-L164)):

```python
request_body = {
    'anthropic_version': 'bedrock-2023-05-31',
    'max_tokens': 500,
    'temperature': 0.1,
    'messages': [{'role': 'user', 'content': full_prompt}],
}
```

- **max_tokens**: 500 (sufficient for routing decisions)
- **temperature**: 0.1 (low for consistent routing)
- **anthropic_version**: bedrock-2023-05-31 (Bedrock Messages API)

## Enabling Bedrock Access

Before using AI routing, you must enable model access in AWS:

1. **Navigate to Bedrock Console**:
   ```bash
   # Open console directly
   https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess
   ```

2. **Enable Claude Sonnet 4.5**:
   - Click "Manage model access" or "Modify model access"
   - Find "Claude Sonnet 4.5" in the list
   - Check the box to enable access
   - Click "Save changes"
   - Wait for access status to show "Access granted" (usually instant)

3. **Verify Access**:
   ```bash
   aws bedrock list-foundation-models --region us-east-1 \
     --query 'modelSummaries[?contains(modelId, `claude-sonnet-4-5`)]'
   ```

## IAM Permissions

The Lambda function requires these Bedrock permissions ([main.tf:198-205](../main.tf#L198-L205)):

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": [
    "arn:aws:bedrock:${region}:*:inference-profile/${bedrock_model_id}",
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0"
  ]
}
```

**Note**: Both ARN formats are included for cross-region inference profile support.

## DynamoDB Routing Configuration

### Table Structure

The routing prompt is stored in DynamoDB with this schema:

```
Table: {project_name}-routing
Partition Key (pk): "CONFIG"
Sort Key (sk): "routing_prompt"

Required Attributes:
- prompt (String): The routing instructions for Claude
- enabled (Boolean): Enable/disable AI routing at runtime
- updated_at (String): ISO 8601 timestamp of last update

Optional Attributes:
- model_id (String): Override default Bedrock model
- temperature (Number): Override default temperature
- max_tokens (Number): Override default max tokens
```

### Example Routing Prompt

Create a simple routing prompt for testing:

```json
{
  "pk": {"S": "CONFIG"},
  "sk": {"S": "routing_prompt"},
  "prompt": {"S": "Prepend [TEST] to email subjects for all incoming email. Return JSON: {\"route_to\": [\"your@gmail.com\"], \"tags\": [\"TEST\"], \"confidence\": 1.0, \"reasoning\": \"Test routing\"}"},
  "enabled": {"BOOL": true},
  "updated_at": {"S": "2025-01-15T12:00:00Z"}
}
```

### Adding Routing Prompt via AWS CLI

```bash
# Set your values
TABLE_NAME="ai-email-routing"
FORWARD_EMAIL="your@gmail.com"

# Create routing-prompt.json
cat > routing-prompt.json <<'EOF'
{
  "pk": {"S": "CONFIG"},
  "sk": {"S": "routing_prompt"},
  "prompt": {"S": "Analyze this email and route it appropriately.\n\nEMAIL CONTENT:\nFrom: {sender}\nSubject: {subject}\nBody: {body}\n\nRESPONSE FORMAT (JSON only):\n{\"route_to\": [\"email@example.com\"], \"tags\": [\"TAG1\"], \"confidence\": 0.95, \"reasoning\": \"Brief explanation\"}"},
  "enabled": {"BOOL": true},
  "updated_at": {"S": "2025-01-15T12:00:00Z"}
}
EOF

# Upload to DynamoDB
aws dynamodb put-item --table-name "$TABLE_NAME" --item file://routing-prompt.json

# Verify
aws dynamodb get-item \
  --table-name "$TABLE_NAME" \
  --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}' \
  --query 'Item.prompt.S' \
  --output text
```

### Advanced Routing Prompt Example

For production use with multiple routing destinations:

```
You are an email routing assistant for a business. Analyze the email and determine routing.

ROUTING RULES:
- Customer support inquiries -> support@example.com
- Account issues -> support@example.com with [ACCOUNT] tag
- Sales inquiries -> sales@example.com
- Job applications -> jobs@example.com with [RECRUITING] tag
- Billing/invoices -> accounting@example.com with [INVOICE] tag
- Security concerns -> security@example.com with [SECURITY] tag

PRIORITY DETECTION:
- Urgent keywords (urgent, critical, emergency) -> Add [URGENT] tag
- Angry/frustrated tone -> Add [ESCALATION] tag

EMAIL CONTENT:
From: {sender}
Subject: {subject}
Body: {body}

Return JSON only (no markdown, no explanations):
{"route_to": ["email@example.com"], "tags": ["TAG1", "TAG2"], "confidence": 0.95, "reasoning": "Brief explanation"}
```

## Troubleshooting Bedrock Issues

### Access Denied Errors

**Error**: `AccessDeniedException` when invoking Bedrock

**Solutions**:
1. Check model access is enabled in Bedrock console
2. Verify Lambda IAM role has `bedrock:InvokeModel` permission
3. Confirm the region supports Claude Sonnet 4.5
4. Check the model ID matches the enabled model

```bash
# Check Lambda role permissions
aws iam get-role-policy \
  --role-name ai-email-lambda-role \
  --policy-name ai-email-lambda-policy \
  --query 'PolicyDocument.Statement[?Action[0]==`bedrock:InvokeModel`]'
```

### Throttling Exceptions

**Error**: `ThrottlingException` or `ServiceQuotaExceededException`

**Solutions**:
1. Request quota increase in AWS Service Quotas
2. Implement exponential backoff (already handled in Lambda)
3. Consider using Claude Haiku for higher throughput
4. Monitor CloudWatch metrics for throttle events

```bash
# Check current quotas
aws service-quotas get-service-quota \
  --service-code bedrock \
  --quota-code L-xxxxxx \
  --region us-east-1
```

### Model Not Found Errors

**Error**: `ValidationException: Could not resolve model`

**Solutions**:
1. Verify model ID in terraform.tfvars matches enabled model
2. Check region supports Claude Sonnet 4.5
3. Try using direct model ARN instead of inference profile
4. Confirm model name spelling (common typo: "sonnet" vs "sonet")

```bash
# List available models in your region
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `anthropic`)].modelId'
```

### AI Returns Invalid JSON

**Error**: `JSONDecodeError` in Lambda logs

**Solutions**:
1. Update routing prompt to explicitly request JSON only
2. Add "Return JSON only (no markdown)" to prompt
3. Check CloudWatch logs for actual AI response
4. Increase max_tokens if response is truncated

**Prompt improvement**:
```
Return ONLY valid JSON with no markdown formatting, no code blocks, no explanations:
{"route_to": ["email@example.com"], "tags": [], "confidence": 0.9, "reasoning": ""}
```

### High Latency

**Issue**: Email forwarding takes >5 seconds

**Solutions**:
1. Switch to Claude Haiku model for faster responses
2. Reduce max_tokens (500 -> 200)
3. Monitor Bedrock response times in CloudWatch
4. Check if cross-region failover is occurring

```bash
# Update to use Claude Haiku
# In terraform.tfvars:
bedrock_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
```

## Cost Optimization

### Pricing Breakdown (as of Jan 2025)

**Claude Sonnet 4.5** (via inference profile):
- Input: $3.00 per million tokens
- Output: $15.00 per million tokens

**Typical email routing request**:
- Input tokens: ~500 (prompt + email content)
- Output tokens: ~50 (JSON response)
- Cost per request: ~$0.0009

**Monthly estimates**:
- 1,000 emails: ~$0.90
- 10,000 emails: ~$9.00
- 100,000 emails: ~$90.00

### Cost Reduction Strategies

1. **Use Claude Haiku** (70% cheaper):
   ```hcl
   bedrock_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
   ```

2. **Reduce max_tokens**:
   - Default: 500 tokens
   - Routing only needs: 100-200 tokens
   - Edit [lambda.py:161](../lambda.py#L161) to reduce

3. **Limit body content**:
   - Current: 2000 characters ([lambda.py:156](../lambda.py#L156))
   - Reduce to 1000 for simpler routing

4. **Cache routing decisions**:
   - Store recent routing decisions in DynamoDB
   - Check cache before calling Bedrock
   - Requires custom implementation

## Monitoring and Logs

### CloudWatch Logs

View AI routing decisions:

```bash
# Follow logs in real-time
aws logs tail /aws/lambda/ai-email-forwarder --follow

# Search for AI routing decisions
aws logs filter-log-events \
  --log-group-name /aws/lambda/ai-email-forwarder \
  --filter-pattern "AI routing decision"

# Count failures
aws logs filter-log-events \
  --log-group-name /aws/lambda/ai-email-forwarder \
  --filter-pattern "AI routing failed" \
  --start-time $(date -u -d '1 hour ago' +%s)000
```

### Key Log Messages

Successful routing:
```
INFO AI routing decision: {'route_to': ['support@example.com'], 'tags': ['URGENT'], 'confidence': 0.95}
INFO AI routing applied - Recipients: ['support@example.com'], Tags: ['URGENT']
```

Fallback to default:
```
INFO AI routing failed or returned no decision, using default
INFO Forwarded {messageId} -> your@gmail.com
```

### Debugging Tips

1. **Enable verbose logging**:
   ```bash
   aws lambda update-function-configuration \
     --function-name ai-email-forwarder \
     --environment "Variables={VERBOSE_LOGGING=true,...}"
   ```

2. **Check DynamoDB prompt**:
   ```bash
   aws dynamodb get-item \
     --table-name ai-email-routing \
     --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}'
   ```

3. **Test Bedrock directly**:
   ```bash
   aws bedrock-runtime invoke-model \
     --model-id us.anthropic.claude-sonnet-4-5-20250929-v1:0 \
     --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":500,"messages":[{"role":"user","content":"Hello"}]}' \
     --region us-east-1 \
     output.json
   ```

## Regional Availability

### Supported Regions for Claude Sonnet 4.5

As of January 2025, Claude Sonnet 4.5 is available in:
- us-east-1 (US East, N. Virginia)
- us-west-2 (US West, Oregon)
- eu-west-1 (Europe, Ireland)
- ap-southeast-1 (Asia Pacific, Singapore)
- ap-northeast-1 (Asia Pacific, Tokyo)

**Note**: Using cross-region inference profiles automatically handles regional availability and failover.

### Checking Regional Support

```bash
# List models available in your region
aws bedrock list-foundation-models \
  --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `claude-sonnet-4-5`)]'

# Check inference profile availability
aws bedrock get-inference-profile \
  --inference-profile-identifier us.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --region us-east-1
```

## Security Best Practices

1. **Limit IAM permissions**: Only grant `bedrock:InvokeModel` for specific model ARNs
2. **Use VPC endpoints**: Route Bedrock traffic through VPC for enhanced security
3. **Encrypt DynamoDB table**: Enable encryption at rest for routing prompts
4. **Monitor API calls**: Track Bedrock invocations via CloudTrail
5. **Rotate credentials**: Use IAM roles, not access keys
6. **Content filtering**: Sanitize email content before sending to Bedrock
7. **Rate limiting**: Implement request throttling to prevent abuse

## Alternative Models

### Claude Haiku (Faster, Cheaper)

**Use case**: High-volume routing with simple rules

```hcl
# terraform.tfvars
bedrock_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
```

**Pros**:
- 3x faster response time
- 70% lower cost
- Same API compatibility

**Cons**:
- Less sophisticated reasoning
- May miss nuanced routing decisions

### Claude Opus (Highest Quality)

**Use case**: Complex routing with advanced sentiment analysis

```hcl
# terraform.tfvars
bedrock_model_id = "us.anthropic.claude-opus-4-20250514-v1:0"
```

**Pros**:
- Best reasoning and accuracy
- Handles complex routing logic
- Better at edge cases

**Cons**:
- Higher latency (~2-3 seconds)
- Higher cost (~3x Sonnet)
- May be overkill for simple routing
