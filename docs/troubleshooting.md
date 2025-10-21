# Troubleshooting Guide

This guide covers common issues and their solutions for the intelligent email forwarding system.

## No Emails Received

### 1. Check MX record points to SES

```bash
dig MX example.org
# Should show: 10 inbound-smtp.us-east-1.amazonaws.com
```

If the MX record is incorrect or missing, verify that Terraform successfully created the DNS records in Route53.

### 2. Verify domain is verified in SES

```bash
aws ses get-identity-verification-attributes --identities example.org
```

The verification status should show "Success". If it shows "Pending", DNS records may not have propagated yet. Wait a few minutes and check again.

### 3. Check Lambda logs for errors

```bash
aws logs tail "$(terraform output -raw lambda_log_group_name)" --follow
```

Look for errors in the Lambda execution logs. Common issues include:
- S3 access denied (check IAM permissions)
- SES sending failures (check SES sandbox status)
- Missing environment variables

## AI Routing Not Working

### 1. Verify AI routing is enabled

```bash
terraform output | grep ai_routing
```

Ensure `ai_routing_enabled` is set to `true` in your `terraform.tfvars`.

### 2. Check Bedrock model access

```bash
aws bedrock list-foundation-models --region us-east-1 | grep claude-sonnet-4-5
```

If the model is not listed, you need to enable model access in the Bedrock console:
```bash
open https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess
```

Enable "Claude Sonnet 4.5" and save.

### 3. Verify routing prompt exists in DynamoDB

```bash
aws dynamodb get-item \
  --table-name "$(terraform output -raw dynamodb_table_name)" \
  --key '{"pk":{"S":"CONFIG"},"sk":{"S":"routing_prompt"}}'
```

If the item doesn't exist, you need to create a routing prompt. See the AI-Powered Routing section in the main README for instructions.

For detailed Bedrock troubleshooting, see [bedrock.md](bedrock.md).

## MCP Server Not Working

### 1. Verify MCP server is deployed

```bash
terraform output mcp_server_url
```

If this command returns an error, the MCP server may not be deployed. The MCP server is deployed automatically with `terraform apply`.

### 2. Test API key authentication

```bash
API_KEY=$(grep MCP_API_KEY .env | cut -d'=' -f2)
MCP_URL=$(terraform output -raw mcp_server_url)

curl -X POST "$MCP_URL" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"method":"tools/list","params":{}}'
```

A successful response should return a JSON list of available tools. If you get a 401 error, the API key is invalid.

### 3. Check MCP server logs

```bash
aws logs tail "$(terraform output -raw mcp_log_group_name)" --follow
```

Look for errors in the MCP server logs. Common issues include:
- API key authentication failures
- DynamoDB access errors
- Invalid JSON-RPC requests

### 4. Verify API key exists in DynamoDB

```bash
TABLE_NAME=$(terraform output -raw dynamodb_table_name)
KEY_HASH=$(echo -n "$API_KEY" | shasum -a 256 | awk '{print $1}')

aws dynamodb get-item \
  --table-name "$TABLE_NAME" \
  --key '{"pk":{"S":"API_KEY"},"sk":{"S":"'$KEY_HASH'"}}'
```

If the item doesn't exist, regenerate the API key:
```bash
./scripts/create-api-key.sh
```

For detailed MCP troubleshooting, see [mcp-server.md](mcp-server.md).

## Multiple Domains Issues

### 1. Previous domain stopped working

Check that the SES receipt rule set `ses-catchall-forwarder-rules` is active:

```bash
aws ses describe-active-receipt-rule-set
```

If it's not active or shows a different rule set, activate it:

```bash
aws ses set-active-receipt-rule-set --rule-set-name ses-catchall-forwarder-rules
```

### 2. Rule conflicts

Ensure each domain uses a unique `project_name` in terraform.tfvars. List all receipt rules to check for conflicts:

```bash
aws ses describe-receipt-rule-set --rule-set-name ses-catchall-forwarder-rules
```

Each domain should have its own rule with a unique name.

### 3. Wrong bucket

Verify the Lambda `S3_PREFIX` environment variable matches the domain name:

```bash
aws lambda get-function-configuration \
  --function-name "$(terraform output -raw lambda_function_name)" \
  --query 'Environment.Variables.S3_PREFIX' \
  --output text
```

The prefix should be `{domain_name}/` (e.g., `example.org/`).

## Common Error Messages

### "AccessDenied" when reading from S3

**Cause**: Lambda function doesn't have permission to read from the S3 bucket.

**Solution**: Check the IAM role attached to the Lambda function:
```bash
aws lambda get-function --function-name "$(terraform output -raw lambda_function_name)" \
  --query 'Configuration.Role'
```

Then verify the role has `s3:GetObject` permission for the bucket.

### "ValidationError: Invalid email address"

**Cause**: The destination email address is not verified in SES (if in sandbox mode).

**Solution**: Either verify the destination email in SES or request production access:
```bash
# Verify email address
aws ses verify-email-identity --email-address user@example.com

# Check sandbox status
aws ses get-account-sending-enabled
```

### "ThrottlingException" from Bedrock

**Cause**: Too many concurrent requests to Bedrock API.

**Solution**: Bedrock has rate limits. If you're processing high volumes of email, consider:
- Requesting a quota increase in the AWS Service Quotas console
- Implementing retry logic with exponential backoff
- Using a faster/cheaper model for lower-priority emails

### "ReceiptRuleSetDoesNotExist"

**Cause**: The SES receipt rule set was deleted or doesn't exist.

**Solution**: Re-run `terraform apply` to recreate the rule set and rules.

## DNS Propagation Issues

### MX records not resolving

DNS changes can take up to 48 hours to propagate, but typically complete within minutes to hours.

Check propagation status:
```bash
# Check from multiple DNS servers
dig @8.8.8.8 MX example.org
dig @1.1.1.1 MX example.org
```

Use online tools to check global DNS propagation:
- https://www.whatsmydns.net/

### DKIM verification pending

DKIM CNAME records must propagate before SES can verify them.

Check DKIM record propagation:
```bash
# Get DKIM tokens from SES
aws ses get-identity-dkim-attributes --identities example.org

# Check each DKIM CNAME record
dig TOKEN._domainkey.example.org CNAME
```

## Performance Issues

### Slow email forwarding (>10 seconds)

**Cause**: AI routing with Bedrock can add 2-5 seconds of latency.

**Solution**:
- Disable AI routing for time-sensitive emails
- Use Claude Haiku instead of Sonnet (faster, cheaper)
- Check Lambda CloudWatch metrics for cold start delays

### Lambda timeout errors

**Cause**: Lambda function timeout set too low (default: 30 seconds).

**Solution**: Increase timeout in `main.tf`:
```hcl
timeout = 60  # Increase to 60 seconds
```

Then run `terraform apply`.

## Getting Help

If you've tried all troubleshooting steps and still have issues:

1. **Check CloudWatch Logs**: Most issues can be diagnosed from Lambda logs
   ```bash
   aws logs tail "$(terraform output -raw lambda_log_group_name)" --follow
   ```

2. **Enable Verbose Logging**: Set `VERBOSE_LOGGING=true` in Lambda environment variables

3. **Review AWS Service Health**: Check if there are any AWS service disruptions
   - https://status.aws.amazon.com/

4. **Verify IAM Permissions**: Ensure the Lambda execution role has all necessary permissions

5. **Test with Simple Configuration**: Disable AI routing and test basic forwarding first

For architecture details and implementation specifics, see [architecture.md](architecture.md).
