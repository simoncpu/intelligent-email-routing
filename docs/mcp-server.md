# MCP Server for Email Routing Management

The MCP (Model Context Protocol) server allows you to manage email routing rules conversationally through Claude Desktop or other MCP clients.

## What is MCP?

Model Context Protocol (MCP) is a standard for connecting AI assistants to external tools and data sources. Our MCP server exposes tools that let you interact with the email routing configuration stored in DynamoDB.

## Routing Rules vs System Prompt

**Important Security Design**: The system uses a two-part prompt structure:

1. **System Prompt Template** (hard-coded in lambda.py):
   - Email content placeholders ({sender}, {subject}, {body})
   - JSON response format requirements
   - Security constraints
   - Cannot be modified by users (prevents prompt injection)

2. **Routing Rules** (configurable via MCP):
   - Business logic (routing destinations, tags, conditions)
   - Stored in DynamoDB
   - Editable through MCP tools
   - Does NOT include email placeholders or JSON format

This separation ensures reliable JSON responses and prevents malicious prompt injection attacks.

## Architecture

```
Claude Desktop (MCP Client) <-> Lambda Function URL <-> MCP Lambda <-> DynamoDB
```

- **Lambda Function URL**: Serverless HTTP endpoint (no API Gateway needed)
- **JSON-RPC 2.0**: Industry-standard protocol for remote procedure calls
- **MCP Protocol 2025-03-26**: Latest Model Context Protocol specification
- **API Key Authentication**: SHA256-hashed keys stored in DynamoDB
- **DynamoDB**: Stores routing prompts, API keys, and version history

## Protocol Implementation

The server implements the MCP lifecycle correctly:

1. **Initialize**: Client sends `initialize` request with protocol version and capabilities
2. **Initialized**: Client sends `notifications/initialized` after receiving server response
3. **Operation**: Normal tool calls using `tools/list` and `tools/call` methods

All requests and responses follow JSON-RPC 2.0 format with proper `jsonrpc`, `id`, `method`, and `params`/`result` fields.

## Available Tools

The MCP server exposes these tools:

1. **get_routing_prompt** - Fetch current routing rules from DynamoDB (business logic only)
2. **update_routing_prompt** - Update routing rules and archive previous version
3. **get_prompt_history** - View previous routing rules versions (last 10)
4. **validate_prompt_syntax** - Validate routing rules (checks for non-empty content and provides suggestions)

**Note**: Tool names still say "prompt" for backward compatibility, but they now work with routing rules (business logic only, not full prompts).

## Setup

### 1. Deploy Infrastructure

Deploy the MCP server with Terraform:

```bash
terraform apply
```

This creates:
- Lambda function for MCP server
- Lambda Function URL (publicly accessible)
- IAM role with DynamoDB permissions
- CloudWatch log group

### 2. Get Function URL

```bash
terraform output mcp_server_url
```

Save this URL - you'll need it for Claude Desktop configuration.

### 3. Create API Key

Run the helper script to create an API key in DynamoDB:

```bash
./scripts/create-api-key.sh
```

This reads the API key from `.env` file, hashes it with SHA256, and stores it in DynamoDB.

The script outputs the API key to use in your Claude Desktop configuration.

### 4. Configure Claude Code

You can configure the MCP server using either the CLI command or manual JSON configuration.

#### Option A: CLI Command (Recommended)

```bash
# Get your MCP server URL
MCP_URL=$(terraform output -raw mcp_server_url)

# Get your API key
API_KEY=$(grep MCP_API_KEY .env | cut -d= -f2)

# Add MCP server to Claude Code
claude mcp add --transport http email-routing "$MCP_URL" \
  --header "Authorization: Bearer $API_KEY"
```

The CLI command automatically configures the server in your Claude Code settings.

#### Option B: Manual JSON Configuration

Edit the Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Linux**: `~/.config/Claude/claude_desktop_config.json`

Add this configuration:

```json
{
  "mcpServers": {
    "email-routing": {
      "type": "http",
      "url": "https://YOUR-FUNCTION-URL.lambda-url.us-east-1.on.aws/",
      "headers": {
        "Authorization": "Bearer YOUR-API-KEY-FROM-ENV-FILE"
      }
    }
  }
}
```

Replace:
- `YOUR-FUNCTION-URL` with output from `terraform output mcp_server_url`
- `YOUR-API-KEY-FROM-ENV-FILE` with the `MCP_API_KEY` value from `.env`

### 5. Verify Connection

Check that the MCP server is connected:

```bash
claude mcp list
```

You should see `email-routing` listed with a green checkmark. If you see a red X, check the troubleshooting section below.

After configuration, restart Claude Desktop if using the manual method.

## Usage Examples

### View Current Routing Rules

```
User: Show me the current email routing rules
Claude: [Uses get_routing_prompt tool to fetch routing rules from DynamoDB]
```

### Update Routing Rules

```
User: Update the routing rules to route customer support emails to support@example.com
Claude: [Helps you write routing rules (business logic only), validates them, then uses update_routing_prompt]
```

Example routing rules:
```
- Customer support inquiries -> support@example.com with [SUPPORT] tag
- Sales emails -> sales@example.com with [SALES] tag
- Urgent keywords -> Add [URGENT] tag
```

**Important**: Do NOT include email content placeholders ({sender}, {subject}, {body}) or JSON format in your routing rules. Those are in the hard-coded system template.

### View Version History

```
User: Show me the routing rules version history
Claude: [Uses get_prompt_history tool to show last 10 versions]
```

### Validate Routing Rules Before Applying

```
User: Check if these routing rules are valid: "Route all support emails to support@example.com"
Claude: [Uses validate_prompt_syntax - validates content and provides suggestions]
```

## API Key Management

### Create Additional API Keys

```bash
# Generate new key
NEW_KEY=$(openssl rand -hex 32)

# Hash it
KEY_HASH=$(echo -n "$NEW_KEY" | shasum -a 256 | awk '{print $1}')

# Store in DynamoDB
TABLE_NAME=$(terraform output -raw dynamodb_table_name)
aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{
        "pk": {"S": "API_KEY"},
        "sk": {"S": "'$KEY_HASH'"},
        "key_name": {"S": "secondary-key"},
        "created_at": {"S": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"},
        "is_active": {"BOOL": true},
        "permissions": {"SS": ["all"]}
    }'

echo "API Key: $NEW_KEY"
```

### Revoke API Key

```bash
TABLE_NAME=$(terraform output -raw dynamodb_table_name)
KEY_HASH="hash-of-key-to-revoke"

aws dynamodb update-item \
    --table-name "$TABLE_NAME" \
    --key '{"pk":{"S":"API_KEY"},"sk":{"S":"'$KEY_HASH'"}}' \
    --update-expression "SET is_active = :false" \
    --expression-attribute-values '{":false":{"BOOL":false}}'
```

### Set Key Expiration

```bash
TABLE_NAME=$(terraform output -raw dynamodb_table_name)
KEY_HASH="hash-of-key"
EXPIRES_AT="2025-12-31T23:59:59Z"

aws dynamodb update-item \
    --table-name "$TABLE_NAME" \
    --key '{"pk":{"S":"API_KEY"},"sk":{"S":"'$KEY_HASH'"}}' \
    --update-expression "SET expires_at = :expires" \
    --expression-attribute-values '{":expires":{"S":"'$EXPIRES_AT'"}}'
```

### Limited Permissions Key

Create a key that can only read prompts (not update):

```bash
# ... same key generation as above ...

aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{
        "pk": {"S": "API_KEY"},
        "sk": {"S": "'$KEY_HASH'"},
        "key_name": {"S": "read-only"},
        "created_at": {"S": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"},
        "is_active": {"BOOL": true},
        "permissions": {"SS": ["get_routing_prompt", "get_prompt_history", "validate_prompt_syntax"]}
    }'
```

## Monitoring

### View MCP Server Logs

```bash
aws logs tail /aws/lambda/ai-email-forwarder-mcp-server --follow
```

### Check API Key Usage

```bash
TABLE_NAME=$(terraform output -raw dynamodb_table_name)

aws dynamodb query \
    --table-name "$TABLE_NAME" \
    --key-condition-expression "pk = :pk" \
    --expression-attribute-values '{":pk":{"S":"API_KEY"}}' \
    --projection-expression "key_name,is_active,last_used_at,created_at"
```

## Troubleshooting

### Connection Failed: "Unknown method: initialize"

This error means the MCP protocol implementation is incomplete. This has been fixed in the current version. If you see this error:

1. Run `terraform apply` to deploy the updated Lambda function
2. Verify the fix with: `curl -X POST <MCP_URL> -H "Authorization: Bearer <API_KEY>" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}}'`
3. You should see a proper JSON-RPC 2.0 response with `protocolVersion`, `capabilities`, and `serverInfo`

### 401 Unauthorized

- Check that API key is correct in Claude Code config
- Verify API key exists and is active in DynamoDB: `aws dynamodb query --table-name ai-email-routing --key-condition-expression "pk = :pk" --expression-attribute-values '{":pk":{"S":"API_KEY"}}'`
- Check that key hasn't expired

### 403 Forbidden

- Check that API key has permissions for the tool you're trying to use
- Update permissions in DynamoDB if needed (see API Key Management section)

### Tools Not Showing in Claude Code

- Run `claude mcp list` to check server status
- If status shows "failed", check logs: `ls -la ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-email-routing/`
- Verify Function URL is correct: `terraform output mcp_server_url`
- Test connection manually: `curl -X POST <MCP_URL> -H "Authorization: Bearer <API_KEY>" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'`

### Lambda Errors

```bash
# Check logs
aws logs tail /aws/lambda/ai-email-mcp-server --follow

# Check function configuration
aws lambda get-function-configuration \
    --function-name ai-email-mcp-server

# Test initialize endpoint
MCP_URL=$(terraform output -raw mcp_server_url)
API_KEY=$(grep MCP_API_KEY .env | cut -d= -f2)
curl -X POST "$MCP_URL" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}}'
```

### Protocol Version Mismatch

The server supports MCP protocol version 2025-03-26. If Claude Code requests a different version:

- The server will respond with its supported version
- Claude Code should negotiate and use a compatible version
- Check logs to see which version Claude Code requested

## Security Considerations

- **API keys stored as SHA256 hashes** - irreversible, cannot retrieve original key
- **HTTPS enforced** - Lambda Function URLs use TLS
- **Per-key permissions** - limit what each key can do
- **Expiration dates** - keys can be time-limited
- **Audit trail** - All access logged in CloudWatch
- **No AWS credentials needed** - MCP clients don't need IAM access

### Production Recommendations

1. **Restrict CORS origins** in [main.tf:404](main.tf#L404) to specific domains
2. **Use limited permissions** for most keys (not "all")
3. **Set expiration dates** on API keys
4. **Rotate keys regularly** (every 90 days recommended)
5. **Monitor usage** via CloudWatch logs
6. **Use separate keys** for different users/teams

## Cost

The MCP server is extremely cost-effective:

- **Lambda Function URL**: Free (no API Gateway charges)
- **Lambda invocations**: ~$0.02/month for 100 prompt updates
- **DynamoDB**: ~$0.01/month for API key storage
- **CloudWatch Logs**: ~$0.01/month

**Total**: ~$0.04/month vs ~$0.38/month with API Gateway (90% savings)

## DynamoDB Schema

### API Keys

```
pk: "API_KEY"
sk: SHA256(api_key)
key_name: string (e.g., "default", "team-a")
created_at: ISO 8601 timestamp
is_active: boolean
expires_at: ISO 8601 timestamp (optional)
permissions: string set (tool names or "all")
last_used_at: ISO 8601 timestamp (updated on each use)
description: string (optional)
```

### Config

```
pk: "CONFIG"
sk: "routing_prompt"
routing_rules: string (routing rules - business logic only)
enabled: boolean
model_id: string (Bedrock model ID)
updated_at: ISO 8601 timestamp
```

### History

```
pk: "HISTORY"
sk: "routing_prompt#TIMESTAMP"
routing_rules: string (archived routing rules)
archived_at: ISO 8601 timestamp
```

## Next Steps

After setting up the MCP server:

1. Test it by asking Claude to show the current routing rules
2. Use Claude to help you write better routing rules (business logic only - no need for email placeholders or JSON format)
3. Iterate on routing rules based on real email traffic
4. Create additional API keys for team members
5. Monitor usage and routing accuracy

**Remember**: You only configure routing rules (business logic). The system template (email placeholders and JSON format) is hard-coded for security.

For more details on email routing and the system template, see [docs/bedrock.md](bedrock.md).
