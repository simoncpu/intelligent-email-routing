import email
import html
import logging
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

import boto3

s3 = boto3.client('s3')
ses = boto3.client('ses')

BUCKET = os.environ['S3_BUCKET']
PREFIX = os.environ.get('S3_PREFIX', 'inbound/')
FORWARD_TO = os.environ['FORWARD_TO']
FROM_ADDRESS = os.environ['FROM_ADDRESS']
VERBOSE_LOGGING = os.environ.get('VERBOSE_LOGGING', 'false').lower() == 'true'

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


def handler(event, context):
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

        # Create forwarding context
        context_text, context_html = create_forwarding_context(
            orig_from, actual_recipient, orig_date
        )

        # Extract display name from original sender for From header
        orig_display_name, _ = parseaddr(orig_from)
        formatted_from = formataddr((orig_display_name, FROM_ADDRESS))

        # Create the multipart message
        msg = MIMEMultipart('mixed')
        msg['From'] = formatted_from
        msg['To'] = FORWARD_TO
        msg['Subject'] = subject
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
            FORWARD_TO,
            resp.get('MessageId'),
        )
        return {'status': 'ok'}
    except Exception as e:
        log.exception('Forward error: %s', e)
        raise
