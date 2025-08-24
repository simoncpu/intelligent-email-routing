variable "project_name" {
  type        = string
  default     = "ses-catchall-forwarder"
  description = "Name prefix for resources"
}

variable "domain_name" {
  type        = string
  description = "Your email domain, e.g. example.org"
}

variable "forward_to_email" {
  type        = string
  description = "Destination address, e.g. myrealemail@gmail.com"
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
