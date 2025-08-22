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

variable "s3_prefix" {
  type        = string
  default     = "inbound/"
  description = "Prefix in S3 bucket to store raw emails"
}
