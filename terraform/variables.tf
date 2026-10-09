variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "AWS CLI profile name (from `aws configure sso`)."
  type        = string
  default     = "cloudhub"
}

variable "name" {
  description = "Name for the instance, security group, and Tailscale hostname. Use something other than your live instance's name when testing."
  type        = string
  default     = "cloudhub-tf"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,40}$", var.name))
    error_message = "Use 1-40 lowercase letters, digits, or hyphens."
  }
}

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 GB) is the minimum for Nextcloud AIO; t3.medium (4 GB) is more comfortable."
  type        = string
  default     = "t3.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume size in GiB (gp3, encrypted)."
  type        = number
  default     = 30
}

variable "swap_gb" {
  description = "Size of the swap file created at boot, in GiB."
  type        = number
  default     = 2
}

variable "tailscale_auth_key" {
  description = "Tailscale auth key. Generate a one-off, pre-approved, short-expiry key in the Tailscale admin console. It is placed in instance user data, so do not reuse it."
  type        = string
  sensitive   = true

  validation {
    condition     = startswith(var.tailscale_auth_key, "tskey-auth-")
    error_message = "Expected a Tailscale auth key starting with tskey-auth-."
  }
}

variable "allow_tailscale_direct_udp" {
  description = "Open UDP 41641 inbound so Tailscale can make direct (non-relayed) connections. Off = zero inbound rules."
  type        = bool
  default     = false
}
