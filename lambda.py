import os
import email
from email.message import EmailMessage
from email.utils import parseaddr
import logging
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


def handler(event, context):
    """
    Triggered by SES receipt rule (not S3). Raw email is stored as:
      s3://BUCKET/PREFIX + SES.mail.messageId
    """
    try:
        record = event['Records'][0]
        ses_record = record['ses']
        mail = ses_record['mail']
        message_id = mail['messageId']

        key = f'{PREFIX}{message_id}'
        log.info('Fetching raw email from s3://%s/%s', BUCKET, key)

        obj = s3.get_object(Bucket=BUCKET, Key=key)
        raw_bytes = obj['Body'].read()

        original = email.message_from_bytes(raw_bytes)
        orig_from = original.get('From', '')
        subject = original.get('Subject', '')

        wrapper = EmailMessage()
        wrapper['From'] = FROM_ADDRESS
        wrapper['To'] = FORWARD_TO
        wrapper['Subject'] = subject
        if orig_from:
            wrapper['Reply-To'] = orig_from

        wrapper.set_content('Forwarded message attached.')

        wrapper.add_attachment(
            raw_bytes,
            maintype='message',
            subtype='rfc822',
            filename='original.eml',
        )

        resp = ses.send_raw_email(RawMessage={'Data': wrapper.as_bytes()})
        log.info(
            'Forwarded %s -> %s; SES MessageId: %s', message_id, FORWARD_TO, resp.get('MessageId'))
        return {'status': 'ok'}
    except Exception as e:
        log.exception('Forward error: %s', e)
        raise
