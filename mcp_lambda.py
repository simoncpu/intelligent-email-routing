"""
MCP Lambda server for AI Email Routing prompt management.

This Lambda function exposes an MCP (Model Context Protocol) server that allows
AI assistants like Claude Desktop to help users interactively manage email
routing prompts stored in DynamoDB.

Authentication: API key validation using SHA256 hashes stored in DynamoDB.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.client("dynamodb")

# Get environment variables
ROUTING_TABLE = os.environ.get("ROUTING_TABLE", "ai-email-routing")


def validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Validate API key by checking SHA256 hash in DynamoDB.

    Args:
        api_key: The API key to validate

    Returns:
        Dict with key_name and permissions if valid, None if invalid
    """
    if not api_key:
        return None

    # Hash the API key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    try:
        # Query DynamoDB for API key
        response = dynamodb.get_item(
            TableName=ROUTING_TABLE, Key={"pk": {"S": "API_KEY"}, "sk": {"S": key_hash}}
        )

        if "Item" not in response:
            return None

        item = response["Item"]

        # Check if key is active
        if not item.get("is_active", {}).get("BOOL", False):
            return None

        # Check expiration date if present
        if "expires_at" in item:
            expires_at = datetime.fromisoformat(
                item["expires_at"]["S"].replace("Z", "+00:00")
            )
            if datetime.now(timezone.utc) > expires_at:
                return None

        # Update last_used_at timestamp
        try:
            dynamodb.update_item(
                TableName=ROUTING_TABLE,
                Key={"pk": {"S": "API_KEY"}, "sk": {"S": key_hash}},
                UpdateExpression="SET last_used_at = :timestamp",
                ExpressionAttributeValues={
                    ":timestamp": {"S": datetime.now(timezone.utc).isoformat()}
                },
            )
        except ClientError:
            # Don't fail validation if timestamp update fails
            pass

        # Return key info
        return {
            "key_name": item.get("key_name", {}).get("S", "unknown"),
            "permissions": item.get("permissions", {}).get("SS", []),
        }

    except ClientError:
        return None


def get_routing_prompt() -> Dict[str, Any]:
    """
    Get current routing rules from DynamoDB.

    Note: Returns routing rules (business logic) stored in DynamoDB.
    The system prompt template (JSON format enforcement) is hard-coded in lambda.py.

    Returns:
        Dict with routing_rules, enabled, model_id, and updated_at
    """
    try:
        response = dynamodb.get_item(
            TableName=ROUTING_TABLE,
            Key={"pk": {"S": "CONFIG"}, "sk": {"S": "routing_prompt"}},
        )

        if "Item" not in response:
            return {
                "error": "Routing configuration not found",
                "routing_rules": None,
                "enabled": False,
                "note": "Use update_routing_prompt to set initial routing rules",
            }

        item = response["Item"]

        # Extract routing rules
        routing_rules = item.get("routing_rules", {}).get("S", "")

        return {
            "routing_rules": routing_rules,
            "enabled": item.get("enabled", {}).get("BOOL", False),
            "model_id": item.get("model_id", {}).get("S", ""),
            "updated_at": item.get("updated_at", {}).get("S", ""),
            "note": "Routing rules define business logic. System prompt (JSON format) is hard-coded for security.",
        }

    except ClientError as e:
        return {"error": f"Failed to get routing rules: {str(e)}"}


def update_routing_prompt(prompt: str) -> Dict[str, Any]:
    """
    Update routing rules in DynamoDB and archive current version.

    Note: This updates the routing rules (business logic) only.
    The system prompt template (JSON format enforcement) is hard-coded for security.

    Args:
        prompt: New routing rules text (business logic for email classification)

    Returns:
        Dict with success status and timestamp
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()

        # Get current routing rules for archiving
        current = get_routing_prompt()
        if "routing_rules" in current and current["routing_rules"]:
            # Archive current version
            try:
                dynamodb.put_item(
                    TableName=ROUTING_TABLE,
                    Item={
                        "pk": {"S": "HISTORY"},
                        "sk": {"S": f"routing_prompt#{timestamp}"},
                        "routing_rules": {"S": current["routing_rules"]},
                        "archived_at": {"S": timestamp},
                    },
                )
            except ClientError:
                # Continue even if archiving fails
                pass

        # Update current routing rules (store in new field name)
        dynamodb.put_item(
            TableName=ROUTING_TABLE,
            Item={
                "pk": {"S": "CONFIG"},
                "sk": {"S": "routing_prompt"},
                "routing_rules": {"S": prompt},
                "enabled": {"BOOL": True},
                "updated_at": {"S": timestamp},
            },
        )

        return {
            "success": True,
            "updated_at": timestamp,
            "note": "Routing rules updated. System prompt template (JSON format) remains hard-coded.",
        }

    except ClientError as e:
        return {"success": False, "error": f"Failed to update routing rules: {str(e)}"}


def get_prompt_history(limit: int = 10) -> Dict[str, Any]:
    """
    Get routing rules version history from DynamoDB.

    Args:
        limit: Maximum number of versions to return

    Returns:
        Dict with list of routing rules versions
    """
    try:
        response = dynamodb.query(
            TableName=ROUTING_TABLE,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": "HISTORY"},
                ":sk_prefix": {"S": "routing_prompt#"},
            },
            ScanIndexForward=False,  # Sort descending (newest first)
            Limit=limit,
        )

        versions = []
        for item in response.get("Items", []):
            routing_rules = item.get("routing_rules", {}).get("S", "")
            versions.append(
                {
                    "routing_rules": routing_rules,
                    "archived_at": item.get("archived_at", {}).get("S", ""),
                }
            )

        return {"versions": versions}

    except ClientError as e:
        return {"error": f"Failed to get routing rules history: {str(e)}"}


def validate_prompt_syntax(prompt: str) -> Dict[str, Any]:
    """
    Validate routing rules syntax.

    Note: Routing rules contain business logic only (routing destinations, tags, conditions).
    Email content placeholders ({sender}, {subject}, {body}) are in the hard-coded system template.

    Args:
        prompt: Routing rules to validate

    Returns:
        Dict with valid flag and any warnings/suggestions
    """
    if not prompt or prompt.strip() == "":
        return {
            "valid": False,
            "errors": ["Routing rules cannot be empty"],
            "help": "Provide routing logic like: 'Route support emails to support@example.com with [SUPPORT] tag'",
        }

    # No placeholder validation needed - those are in system template
    # Just provide helpful validation
    suggestions = []

    if len(prompt) < 20:
        suggestions.append("Routing rules seem very short. Consider adding more detailed routing logic.")

    if "route" not in prompt.lower() and "->" not in prompt:
        suggestions.append("Routing rules should specify where to route emails (e.g., 'support@example.com' or 'sales team').")

    result = {
        "valid": True,
        "message": "Routing rules are valid",
        "note": "Email placeholders ({sender}, {subject}, {body}) are handled by the system template.",
    }

    if suggestions:
        result["suggestions"] = suggestions

    return result


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for MCP server.

    Validates API key and routes MCP requests to appropriate functions.

    Args:
        event: Lambda event containing MCP request
        context: Lambda context

    Returns:
        HTTP response with MCP result
    """
    # Extract API key from Authorization header
    headers = event.get("headers", {})
    auth_header = headers.get("authorization", headers.get("Authorization", ""))

    # Strip "Bearer " prefix if present
    api_key = auth_header.replace("Bearer ", "").strip()

    # Validate API key
    if not api_key:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing API key"}),
        }

    key_info = validate_api_key(api_key)
    if not key_info:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid or expired API key"}),
        }

    # Parse JSON-RPC 2.0 request
    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: Invalid JSON in request body"
                }
            }),
        }

    # Validate JSON-RPC 2.0 format
    jsonrpc_version = body.get("jsonrpc", "")
    if jsonrpc_version != "2.0":
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32600,
                    "message": "Invalid Request: Must use JSON-RPC 2.0"
                }
            }),
        }

    # Extract JSON-RPC fields
    request_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # Check permissions (skip for initialize and notifications)
    if method not in ["initialize", "notifications/initialized"]:
        permissions = key_info.get("permissions", [])
        if permissions and method not in permissions and "all" not in permissions:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"API key does not have permission for method: {method}"
                    }
                }),
            }

    # Route to appropriate function
    if method == "initialize":
        # Handle MCP initialization
        client_info = params.get("clientInfo", {})
        client_version = params.get("protocolVersion", "2025-03-26")

        # Return server capabilities and info
        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "email-routing-mcp",
                "version": "1.0.0"
            },
            "instructions": "MCP server for managing AI email routing prompts. Use tools to view and update routing configuration."
        }
    elif method == "notifications/initialized":
        # Client signals it's ready - no response needed for notifications
        return {
            "statusCode": 204,
            "headers": {"Content-Type": "application/json"},
            "body": ""
        }
    elif method == "tools/list":
        # Return list of available MCP tools
        result = {
            "tools": [
                {
                    "name": "get_routing_prompt",
                    "description": "Get current email routing rules from DynamoDB. Returns business logic for routing (destinations, tags, conditions). System prompt template (JSON format) is hard-coded for security.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "update_routing_prompt",
                    "description": "Update email routing rules in DynamoDB. Provide only business logic (where to route, what tags to add). Do NOT include email content placeholders or JSON format - those are in the hard-coded system template.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Routing rules defining business logic (e.g., 'Route support emails to support@example.com with [SUPPORT] tag')"
                            }
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": "get_prompt_history",
                    "description": "Get routing rules version history (last 10 versions by default)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"limit": {"type": "number", "default": 10}},
                    },
                },
                {
                    "name": "validate_prompt_syntax",
                    "description": "Validate routing rules syntax. Checks that rules are non-empty and provides suggestions. No need to include {sender}, {subject}, {body} placeholders - those are in the system template.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Routing rules to validate"
                            }
                        },
                        "required": ["prompt"],
                    },
                },
            ]
        }
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name == "get_routing_prompt":
            tool_result = get_routing_prompt()
        elif tool_name == "update_routing_prompt":
            tool_result = update_routing_prompt(tool_args.get("prompt", ""))
        elif tool_name == "get_prompt_history":
            tool_result = get_prompt_history(tool_args.get("limit", 10))
        elif tool_name == "validate_prompt_syntax":
            tool_result = validate_prompt_syntax(tool_args.get("prompt", ""))
        else:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }),
            }

        # Wrap tool result in MCP content format
        result = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(tool_result, indent=2)
                }
            ]
        }
    else:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}"
                }
            }),
        }

    # Return successful JSON-RPC 2.0 response
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }),
    }
