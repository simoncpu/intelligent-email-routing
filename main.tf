terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4.0"
    }
  }
}

provider "aws" {
  region = var.region
}

############################
# S3 bucket for raw emails #
############################

resource "aws_s3_bucket" "mail" {
  bucket        = var.s3_bucket
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "mail" {
  bucket                  = aws_s3_bucket.mail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_policy" "mail" {
  bucket = aws_s3_bucket.mail.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Sid       = "AllowSESPuts",
      Effect    = "Allow",
      Principal = { Service = "ses.amazonaws.com" },
      Action    = ["s3:PutObject"],
      Resource  = "${aws_s3_bucket.mail.arn}/*",
      Condition = {
        StringEquals = {
          "aws:Referer" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
}

############################################
# Route53 Hosted Zone - Use existing zone
############################################

data "aws_route53_zone" "main" {
  name = var.domain_name
}

############################################
# SES domain identity + DKIM + DNS automation
############################################

resource "aws_ses_domain_identity" "this" {
  domain = var.domain_name
}

resource "aws_ses_domain_dkim" "this" {
  domain = aws_ses_domain_identity.this.domain
}


# Domain verification TXT records
resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "_amazonses.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = [aws_ses_domain_identity.this.verification_token]
}


# DKIM CNAME records (3 records for main domain email authentication)
resource "aws_route53_record" "dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${aws_ses_domain_dkim.this.dkim_tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = ["${aws_ses_domain_dkim.this.dkim_tokens[count.index]}.dkim.amazonses.com"]
}


# SES domain identity verification (waits for DNS propagation)
resource "aws_ses_domain_identity_verification" "this" {
  domain = aws_ses_domain_identity.this.id
  depends_on = [
    aws_route53_record.ses_verification,
    aws_route53_record.dkim
  ]
  timeouts {
    create = "5m"
  }
}


# Configure custom MAIL FROM domain
resource "aws_ses_domain_mail_from" "this" {
  domain           = aws_ses_domain_identity.this.domain
  mail_from_domain = "forwarder.${var.domain_name}"
  behavior_on_mx_failure = "RejectMessage"
}

############################################
# Lambda IAM role/policy
############################################

resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = ["s3:GetObject"],
        Resource = "${aws_s3_bucket.mail.arn}/*"
      },
      {
        Effect = "Allow",
        Action = ["ses:SendRawEmail"],
        Resource = "*"
      }
    ]
  })
}

############################
# Lambda function (Python)
############################

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda.py"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "forwarder" {
  function_name = "${var.project_name}-forwarder"
  role          = aws_iam_role.lambda.arn
  handler       = "lambda.handler"
  runtime       = "python3.13"
  filename      = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout       = 30
  environment {
    variables = {
      S3_BUCKET       = aws_s3_bucket.mail.bucket
      S3_PREFIX       = "${var.domain_name}/"
      FORWARD_TO      = var.forward_to_email
      FROM_ADDRESS    = "forwarder@forwarder.${var.domain_name}"
      VERBOSE_LOGGING = "false"
    }
  }
  depends_on = [
    aws_s3_bucket_policy.mail,
    aws_ses_domain_identity_verification.this
  ]
}

############################################
# SES receipt rule set (S3 -> Lambda)
############################################

resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = "${var.project_name}-rules"
}

resource "aws_ses_active_receipt_rule_set" "active" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_lambda_permission" "allow_ses_unscoped" {
  statement_id  = "AllowSESToInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.forwarder.function_name
  principal     = "ses.amazonaws.com"
}

resource "aws_ses_receipt_rule" "catchall" {
  name          = "catchall-rule"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  enabled       = true

  # Match the whole domain (catch-all)
  recipients    = [var.domain_name]

  scan_enabled  = true
  tls_policy    = "Optional"

  s3_action {
    bucket_name       = aws_s3_bucket.mail.bucket
    object_key_prefix = "${var.domain_name}/"
    position          = 1
  }

  lambda_action {
    function_arn    = aws_lambda_function.forwarder.arn
    invocation_type = "Event"
    position        = 2
  }
}

resource "aws_lambda_permission" "allow_ses_scoped" {
  statement_id  = "AllowSESToInvokeScoped"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.forwarder.function_name
  principal     = "ses.amazonaws.com"
  source_arn    = aws_ses_receipt_rule.catchall.arn
}

#########################################################################
# S3 lifecycle - auto-delete after 30 days
# You may comment out the section below if you want to keep your emails.
#########################################################################
resource "aws_s3_bucket_lifecycle_configuration" "mail" {
  bucket = aws_s3_bucket.mail.id
  rule {
    id     = "expire-raw"
    status = "Enabled"
    filter { prefix = "${var.domain_name}/" }
    expiration { days = 30 }
  }
}

############################################
# Additional DNS records for email delivery
############################################

# MX record for receiving emails
resource "aws_route53_record" "mx" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "MX"
  ttl     = 300
  records = ["10 inbound-smtp.${var.region}.amazonaws.com"]
}

# MX record for MAIL FROM domain (for bounce handling)
resource "aws_route53_record" "mail_from_mx" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "forwarder.${var.domain_name}"
  type    = "MX"
  ttl     = 300
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

# SPF record for sender authentication
resource "aws_route53_record" "spf" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com -all"]
}

# SPF record for MAIL FROM domain
resource "aws_route53_record" "mail_from_spf" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "forwarder.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com -all"]
}

# DMARC record for email security policy
resource "aws_route53_record" "dmarc" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["v=DMARC1; p=quarantine; pct=100; rua=mailto:${var.dmarc_rua_email}; sp=none; aspf=r;"]
}
