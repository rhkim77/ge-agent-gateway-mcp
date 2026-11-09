## --------------------------------------------------------------
## Mandatory variable definitions
## --------------------------------------------------------------

variable "gcp_project_id" {
  type        = string
  description = "The GCP project ID to create resources in."
  default     = "cymbal-ge-agw-demo"
}

variable "gcp_region" {
  type        = string
  description = "Region to create resources in (must be us-central1 for Agent Registry & Agent Gateway)."
  default     = "us-central1"
}

variable "gcp_zone" {
  type        = string
  description = "Zone to create resources in."
  default     = "us-central1-a"
}

variable "project_0_console_url" {
  type        = string
  description = "Lab Console"
  default     = "https://console.cloud.google.com"
}

variable "user_0_password" {
  type        = string
  description = "User 0 Password"
  default     = "Password"
}

variable "user_0_username" {
  type        = string
  description = "User 0"
  default     = "User 0"
}

variable "instance_name" {
  description = "VM instance name"
  type        = string
  default     = "ag-vm"
}

variable "machine_type" {
  description = "Machine type"
  type        = string
  default     = "e2-standard-8"
}

variable "disk_size" {
  description = "Boot disk size (GB)"
  type        = number
  default     = 100
}

variable "event_code" {
  type        = string
  description = "Event Code CE ID and name"
  default     = "ce-ge-agent-gateway-mcp-governance"
}

variable "local_username" {
  type        = string
  description = "lab username"
  default     = "student"
}

variable "ssh_pvt_key" {
  type        = string
  description = "The SSH key for user"
  default     = ""
}
