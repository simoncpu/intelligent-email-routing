#!/bin/bash
#
# Create MCP API key in DynamoDB
#
# Usage: ./scripts/create-api-key.sh [api_key]
#
# If no API key provided, reads from .env file

set -e

# Get table name from Terraform output
TABLE_NAME=$(terraform output -raw dynamodb_table_name 2>/dev/null || echo "ai-email-routing")

# Get API key from argument or .env file
if [ -n "$1" ]; then
    API_KEY="$1"
elif [ -f .env ]; then
    API_KEY=$(grep MCP_API_KEY .env | cut -d'=' -f2)
else
    echo "Error: No API key provided and .env file not found"
    echo "Usage: $0 [api_key]"
    exit 1
fi

if [ -z "$API_KEY" ]; then
    echo "Error: API key is empty"
    exit 1
fi

# Hash the API key with SHA256
KEY_HASH=$(echo -n "$API_KEY" | shasum -a 256 | awk '{print $1}')

# Get current timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Create DynamoDB item
echo "Creating API key in DynamoDB..."
echo "Table: $TABLE_NAME"
echo "Key hash: $KEY_HASH"

aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item "{
        \"pk\": {\"S\": \"API_KEY\"},
        \"sk\": {\"S\": \"$KEY_HASH\"},
        \"key_name\": {\"S\": \"default\"},
        \"created_at\": {\"S\": \"$TIMESTAMP\"},
        \"is_active\": {\"BOOL\": true},
        \"permissions\": {\"SS\": [\"all\"]},
        \"description\": {\"S\": \"Initial MCP API key for prompt management\"}
    }"

echo ""
echo "API key created successfully!"
echo ""
echo "Use this key in Claude Desktop configuration:"
echo "Authorization: Bearer $API_KEY"
echo ""
echo "To revoke this key later, run:"
echo "aws dynamodb update-item --table-name $TABLE_NAME --key '{\"pk\":{\"S\":\"API_KEY\"},\"sk\":{\"S\":\"$KEY_HASH\"}}' --update-expression \"SET is_active = :false\" --expression-attribute-values '{\":false\":{\"BOOL\":false}}'"
