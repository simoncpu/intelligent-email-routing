variable "project_name" {
  type        = string
  default     = "ai-email"
  description = "Name prefix for resources"
}

variable "domain_name" {
  type        = string
  description = "Your email domain, e.g. example.org"
}

variable "forward_to_email" {
  type        = string
  description = "Destination address, e.g. example@gmail.com"
}

variable "region" {
  type        = string
  default     = "us-east-1"
  description = "SES receiving region (e.g., us-east-1)"
}

variable "s3_bucket" {
  type        = string
  description = "S3 bucket name for storing raw emails from multiple domains"
}

variable "dmarc_rua_email" {
  type        = string
  description = "Email address for DMARC aggregate reports (e.g., re+eddisiahumt@dmarc.postmarkapp.com)"
}

variable "ai_routing_enabled" {
  type        = bool
  default     = false
  description = "Enable AI-powered email routing using AWS Bedrock"
}

variable "bedrock_model_id" {
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
  description = "AWS Bedrock inference profile for email analysis (Claude Sonnet 4.5)"
}

variable "routing_fallback_email" {
  type        = string
  default     = ""
  description = "Fallback email address if AI routing fails (uses forward_to_email if empty)"
}
