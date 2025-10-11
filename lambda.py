import email
import html
import json
import logging
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
ses = boto3.client('ses')
dynamodb = boto3.client('dynamodb')
bedrock = boto3.client('bedrock-runtime')

BUCKET = os.environ['S3_BUCKET']
PREFIX = os.environ.get('S3_PREFIX', 'inbound/')
FORWARD_TO = os.environ['FORWARD_TO']
FROM_ADDRESS = os.environ['FROM_ADDRESS']
VERBOSE_LOGGING = os.environ.get('VERBOSE_LOGGING', 'false').lower() == 'true'
AI_ROUTING_ENABLED = os.environ.get('AI_ROUTING_ENABLED', 'false').lower() == 'true'
ROUTING_TABLE = os.environ.get('ROUTING_TABLE', '')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')

log = logging.getLogger()
log.setLevel(logging.DEBUG if VERBOSE_LOGGING else logging.INFO)


def extract_email_content(original_msg):
    """
    Extract plain text and HTML content from an email message.
    """
    text_content = ""
    html_content = ""

    if original_msg.is_multipart():
        for part in original_msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition', ''))

            # Skip attachments
            if 'attachment' in content_disposition:
                continue

            if content_type == 'text/plain':
                text_content = part.get_payload(decode=True).decode(
                    'utf-8', errors='ignore'
                )
            elif content_type == 'text/html':
                html_content = part.get_payload(decode=True).decode(
                    'utf-8', errors='ignore'
                )
    else:
        # Simple single-part message
        if original_msg.get_content_type() == 'text/plain':
            text_content = original_msg.get_payload(decode=True).decode(
                'utf-8', errors='ignore'
            )
        elif original_msg.get_content_type() == 'text/html':
            html_content = original_msg.get_payload(decode=True).decode(
                'utf-8', errors='ignore'
            )

    return text_content, html_content


def create_forwarding_context(orig_from, orig_to, orig_date):
    """
    Create forwarding context message to prepend to the original content.
    """
    context_text = f"""---------- Forwarded message ----------
From: {orig_from}
To: {orig_to}
Date: {orig_date}

"""

    context_html = f"""<div style="border: 1px solid #ccc; padding: 10px; \
margin: 10px 0; background-color: #f9f9f9;">
<strong>---------- Forwarded message ----------</strong><br>
<strong>From:</strong> {html.escape(orig_from)}<br>
<strong>To:</strong> {html.escape(orig_to)}<br>
<strong>Date:</strong> {html.escape(orig_date)}<br>
</div>
"""

    return context_text, context_html


def get_routing_prompt():
    """
    Fetch routing prompt from DynamoDB table.
    Returns the prompt string or None if not found/disabled.
    """
    if not ROUTING_TABLE:
        log.warning('ROUTING_TABLE not configured')
        return None

    try:
        response = dynamodb.get_item(
            TableName=ROUTING_TABLE,
            Key={'pk': {'S': 'CONFIG'}, 'sk': {'S': 'routing_prompt'}},
        )

        if 'Item' not in response:
            log.warning('Routing prompt not found in DynamoDB')
            return None

        item = response['Item']

        # Check if routing is enabled
        if 'enabled' in item and item['enabled'].get('BOOL') is False:
            log.info('AI routing disabled in DynamoDB config')
            return None

        # Extract prompt
        if 'prompt' not in item:
            log.warning('Prompt field not found in DynamoDB item')
            return None

        prompt = item['prompt'].get('S', '')
        log.info('Retrieved routing prompt from DynamoDB')
        return prompt

    except ClientError as e:
        log.error('DynamoDB error fetching routing prompt: %s', e)
        return None
    except Exception as e:
        log.error('Unexpected error fetching routing prompt: %s', e)
        return None


def get_ai_routing_decision(email_content):
    """
    Use Bedrock Claude to determine email routing.
    Returns dict with route_to, tags, confidence, reasoning or None on failure.
    """
    try:
        # Get routing prompt from DynamoDB
        routing_prompt = get_routing_prompt()
        if not routing_prompt:
            log.info('No routing prompt available, skipping AI routing')
            return None

        # Prepare email content for analysis
        sender = email_content.get('sender', '')
        subject = email_content.get('subject', '')
        body = email_content.get('body', '')

        # Build the full prompt
        full_prompt = routing_prompt.replace('{sender}', sender)
        full_prompt = full_prompt.replace('{subject}', subject)
        full_prompt = full_prompt.replace('{body}', body[:2000])  # Limit body length

        # Prepare Bedrock request
        request_body = {
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': 500,
            'temperature': 0.1,
            'messages': [{'role': 'user', 'content': full_prompt}],
        }

        log.debug('Calling Bedrock with model: %s', BEDROCK_MODEL_ID)

        # Call Bedrock
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID, body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())
        ai_response = response_body['content'][0]['text']

        log.debug('AI response: %s', ai_response)

        # Try to parse JSON from AI response
        # Look for JSON block in the response
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            log.warning('No JSON found in AI response')
            return None

        json_str = ai_response[json_start:json_end]
        routing_decision = json.loads(json_str)

        # Validate response structure
        if 'route_to' not in routing_decision:
            log.warning('AI response missing route_to field')
            return None

        log.info(
            'AI routing decision: %s',
            {
                'route_to': routing_decision.get('route_to'),
                'tags': routing_decision.get('tags', []),
                'confidence': routing_decision.get('confidence', 0),
            },
        )

        return routing_decision

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code in ['ThrottlingException', 'ServiceQuotaExceededException']:
            log.error('Bedrock throttling/quota error: %s', e)
        else:
            log.error('Bedrock client error: %s', e)
        return None
    except json.JSONDecodeError as e:
        log.error('Failed to parse AI response as JSON: %s', e)
        return None
    except Exception as e:
        log.error('Unexpected error in AI routing: %s', e)
        return None


def handler(event, context):  # pylint: disable=unused-argument
    """
    Triggered by SES receipt rule (not S3). Raw email is stored as:
      s3://BUCKET/PREFIX + SES.mail.messageId
    """
    try:
        record = event['Records'][0]
        ses_record = record['ses']
        mail = ses_record['mail']
        receipt = ses_record['receipt']
        message_id = mail['messageId']

        # Get the actual recipient email from SES event
        recipients = receipt['recipients']
        actual_recipient = recipients[0] if recipients else ''

        key = f'{PREFIX}{message_id}'
        log.info('Fetching raw email from s3://%s/%s', BUCKET, key)

        obj = s3.get_object(Bucket=BUCKET, Key=key)
        raw_bytes = obj['Body'].read()

        original = email.message_from_bytes(raw_bytes)
        orig_from = original.get('From', '')
        orig_date = original.get('Date', '')
        subject = original.get('Subject', '')

        # Extract original email content
        text_content, html_content = extract_email_content(original)

        # Determine routing based on AI if enabled
        forward_to_addresses = [FORWARD_TO]
        subject_tags = ''

        if AI_ROUTING_ENABLED:
            log.info('AI routing enabled, analyzing email content')
            routing_decision = get_ai_routing_decision(
                {'sender': orig_from, 'subject': subject, 'body': text_content}
            )

            if routing_decision and routing_decision.get('route_to'):
                # Apply AI routing decision
                forward_to_addresses = routing_decision['route_to']
                tags = routing_decision.get('tags', [])
                subject_tags = ' '.join(f'[{tag}]' for tag in tags)

                log.info(
                    'AI routing applied - Recipients: %s, Tags: %s, subject_tags: "%s"',
                    forward_to_addresses,
                    tags,
                    subject_tags,
                )
            else:
                # Fallback to default forwarding
                log.info('AI routing failed or returned no decision, using default')

        # Apply subject tags if any
        final_subject = f'{subject_tags} {subject}' if subject_tags else subject
        log.info('Email subject - final: "%s", original: "%s", tags: "%s"', final_subject, subject, subject_tags)

        # Create forwarding context
        context_text, context_html = create_forwarding_context(
            orig_from, actual_recipient, orig_date
        )

        # Extract display name from original sender for From header
        orig_display_name, _ = parseaddr(orig_from)
        formatted_from = formataddr((orig_display_name, FROM_ADDRESS))

        # Send email to each recipient
        for recipient in forward_to_addresses:
            # Create the multipart message
            msg = MIMEMultipart('mixed')
            msg['From'] = formatted_from
            msg['To'] = recipient
            msg['Subject'] = final_subject
            if orig_from:
                msg['Reply-To'] = orig_from

            # Create the main body with original content
            body_multipart = MIMEMultipart('alternative')

            # Add text version
            if text_content:
                full_text = context_text + text_content
            else:
                full_text = context_text + "(Original message had no text content)"
            body_multipart.attach(MIMEText(full_text, 'plain', 'utf-8'))

            # Add HTML version if available
            if html_content:
                full_html = context_html + html_content
                body_multipart.attach(MIMEText(full_html, 'html', 'utf-8'))
            elif text_content:
                # Convert text to HTML if no HTML version exists
                text_as_html = text_content.replace('\n', '<br>\n')
                full_html = (
                    context_html
                    + '<div style="white-space: pre-wrap; '
                    + f'font-family: monospace;">{text_as_html}</div>'
                )
                body_multipart.attach(MIMEText(full_html, 'html', 'utf-8'))

            # Attach the body to the main message
            msg.attach(body_multipart)

            # Attach the original email as reference
            original_attachment = MIMEApplication(
                raw_bytes, _subtype='rfc822', name='original.eml'
            )
            original_attachment.add_header(
                'Content-Disposition', 'attachment', filename='original.eml'
            )
            msg.attach(original_attachment)

            resp = ses.send_raw_email(RawMessage={'Data': msg.as_bytes()})
            log.info(
                'Forwarded %s -> %s; SES MessageId: %s',
                message_id,
                recipient,
                resp.get('MessageId'),
            )

        return {'status': 'ok'}
    except Exception as e:
        log.exception('Forward error: %s', e)
        raise
