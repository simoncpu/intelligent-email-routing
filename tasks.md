# AI Email Routing Implementation Tasks

**Reference**: See [email-copilot.md](email-copilot.md) for detailed implementation specifications.

## Phase 1: Infrastructure Setup

- [x] Add AI routing variables to variables.tf
  - [x] ai_routing_enabled (bool, default: false)
  - [x] bedrock_model_id (string, default: Claude Haiku)
  - [x] routing_fallback_email (string, optional)

- [x] Create DynamoDB table in main.tf
  - [x] Define table resource with composite key (pk/sk)
  - [x] Set billing mode to PAY_PER_REQUEST
  - [x] Add tags for resource identification
  - [x] Use hierarchical key design for multi-purpose storage

- [x] Update Lambda IAM permissions in main.tf
  - [x] Add DynamoDB GetItem and Query permissions
  - [x] Add Bedrock InvokeModel permission for Claude model
  - [x] Reference DynamoDB table ARN in policy

- [x] Update Lambda environment variables in main.tf
  - [x] Add ROUTING_TABLE variable
  - [x] Add AI_ROUTING_ENABLED variable
  - [x] Add BEDROCK_MODEL_ID variable

## Phase 2: Lambda Function Enhancement

- [x] Add Bedrock and DynamoDB clients to lambda.py
  - [x] Import boto3 clients for bedrock-runtime and dynamodb
  - [x] Initialize clients at module level

- [x] Implement get_routing_prompt() function
  - [x] Fetch routing prompt from DynamoDB table
  - [x] Handle table read errors gracefully
  - [x] Return None if prompt not found or disabled

- [x] Implement get_ai_routing_decision() function
  - [x] Prepare email content (sender, subject, body) for AI analysis
  - [x] Build prompt with routing instructions from DynamoDB
  - [x] Call Bedrock Claude model via InvokeModel API
  - [x] Parse JSON response with route_to, tags, confidence, reasoning
  - [x] Handle AI errors and return None on failure

- [x] Update handler() function with AI routing logic
  - [x] Check if AI_ROUTING_ENABLED environment variable is true
  - [x] Call get_ai_routing_decision() with email content
  - [x] Apply AI routing: set forward addresses and subject tags
  - [x] Implement fallback to default forwarding if AI fails
  - [x] Log routing decisions with confidence scores

- [x] Add comprehensive error handling
  - [x] Catch Bedrock throttling and quota errors
  - [x] Catch DynamoDB access errors
  - [x] Ensure emails always forward (graceful degradation)

## Phase 3: Initial Deployment & Testing

- [x] Deploy infrastructure with AI disabled
  - [x] Set ai_routing_enabled = false in terraform.tfvars
  - [x] Run terraform plan to review changes
  - [x] Run terraform apply to deploy infrastructure
  - [x] Verify DynamoDB table creation
  - [x] Verify Lambda has updated permissions

- [x] Configure initial routing prompt in DynamoDB
  - [x] Create routing_prompt item with simple test rule
  - [x] Use AWS CLI or Console to add DynamoDB item
  - [x] Set enabled = true, model_id, temperature, max_tokens
  - [x] Start with basic rule: "Prepend [TEST] to all email subjects"

- [x] Test standard forwarding still works
  - [x] Send test email to catch-all address
  - [x] Verify email forwards to default recipient
  - [x] Check CloudWatch logs for any errors

## Phase 4: AI Routing Activation

- [x] Enable AI routing
  - [x] Set ai_routing_enabled = true in terraform.tfvars
  - [x] Run terraform apply to update Lambda environment

- [x] Fix infrastructure issues
  - [x] Fix CloudWatch Logs IAM permissions (added :* for log streams)
  - [x] Update routing prompt to return proper JSON format
  - [x] Update to Claude Sonnet 4.5 cross-region inference profile (us.anthropic.claude-sonnet-4-5-20250929-v1:0)
  - [x] Fix IAM permissions for inference profile (required both profile and foundation model ARNs)
  - [x] Fix cross-region permissions (used wildcard * for region in foundation model ARN)

- [x] Test basic AI routing
  - [x] Send test email with simple content
  - [x] Verify [TEST] tag is prepended to subject
  - [x] Check CloudWatch logs for AI routing decision
  - [x] Verify fallback works if AI fails (confirmed - falls back to default)

- [x] Update routing prompt with advanced rules
  - [x] Add classification rules (support, sales, jobs, etc.)
  - [x] Add priority tagging rules (URGENT, ESCALATION)
  - [x] Add sentiment and VIP detection
  - [x] Update DynamoDB item with comprehensive prompt

- [x] Test advanced routing scenarios (manual testing)
  - [x] Customer support inquiry -> Correctly tagged with [SUPPORT]
  - [x] Sales inquiry -> Correctly tagged with [SALES]
  - [x] Urgent email -> Correctly tagged with [URGENT]
  - [x] Angry tone -> Correctly tagged with [ESCALATION]
  - [x] Job application -> Correctly tagged with [RECRUITING]

## Phase 5: Monitoring & Optimization

- [ ] Set up CloudWatch monitoring
  - [ ] Create metrics for AI routing success/failure rate
  - [ ] Track average processing time
  - [ ] Monitor confidence score distribution
  - [ ] Track routing destination frequencies

- [ ] Review and optimize
  - [ ] Analyze CloudWatch logs for routing accuracy
  - [ ] Tune routing prompt based on real emails
  - [ ] Adjust confidence thresholds if needed
  - [ ] Monitor Bedrock costs and usage

- [ ] Document deployment
  - [ ] Update README with AI routing setup instructions
  - [ ] Document DynamoDB schema and prompt format
  - [ ] Add troubleshooting guide for AI routing issues
  - [ ] Include cost monitoring recommendations

## Phase 6: Production Hardening

- [ ] Implement additional safeguards
  - [ ] Add input validation for AI responses
  - [ ] Implement rate limiting if needed
  - [ ] Add circuit breaker for repeated AI failures
  - [ ] Test with high email volume

- [ ] Security review
  - [ ] Verify minimal IAM permissions
  - [ ] Ensure no email content logged inappropriately
  - [ ] Review DynamoDB encryption settings
  - [ ] Audit Bedrock access patterns

- [ ] Create runbook
  - [ ] Document how to disable AI routing quickly
  - [ ] Document how to update routing rules
  - [ ] Document how to troubleshoot AI failures
  - [ ] Include emergency contact procedures

## Notes

- Start with AI disabled to ensure infrastructure deploys correctly
- Use simple routing prompt first, then gradually increase complexity
- Always maintain fallback to default forwarding
- Monitor costs closely during initial rollout
- Keep routing prompt in DynamoDB for easy updates without redeployment
