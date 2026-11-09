data "google_project" "project" {
  project_id = var.gcp_project_id
}

############################
# APIs
############################

resource "google_project_service" "run" {
  project = var.gcp_project_id
  service = "run.googleapis.com"
}

resource "google_project_service" "vpcaccess" {
  project = var.gcp_project_id
  service = "vpcaccess.googleapis.com"
}

resource "google_project_service" "compute" {
  project = var.gcp_project_id
  service = "compute.googleapis.com"
}

resource "time_sleep" "wait_for_vpcaccess_api" {
  depends_on = [
    google_project_service.vpcaccess
  ]

  create_duration = "90s"
}

############################
# VPC CONNECTOR (shared)
############################

resource "google_vpc_access_connector" "connector" {
  name          = "shared-cloudrun-connector"
  region        = var.gcp_region
  network       = "default"
  ip_cidr_range = "10.8.0.0/28"

  min_instances = 2
  max_instances = 5
  depends_on = [
    time_sleep.wait_for_vpcaccess_api
  ]
}

############################
# PSC-I SUBNET (/26) & CLOUD NAT STATIC IP (/32) FOR AGENT GATEWAY
############################

resource "google_compute_subnetwork" "psci_subnet" {
  name          = "cymbal-agw-psci-subnet"
  ip_cidr_range = "10.240.10.0/26"
  region        = var.gcp_region
  network       = "default"
  purpose       = "PRIVATE"
  depends_on    = [google_project_service.project_0]
}

resource "google_compute_address" "agw_egress_ip" {
  name         = "cymbal-aws-mcp-egress-ip"
  region       = var.gcp_region
  address_type = "EXTERNAL"
  depends_on   = [google_project_service.project_0]
}

############################
# CLOUD ROUTER & CLOUD NAT
############################

resource "google_compute_router" "router" {
  name       = "cymbal-agw-nat-router"
  region     = var.gcp_region
  network    = "default"
  depends_on = [google_project_service.project_0]
}

resource "google_compute_router_nat" "nat" {
  name                               = "cymbal-agw-nat-gw"
  router                             = google_compute_router.router.name
  region                             = var.gcp_region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.agw_egress_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ALL"
  }
  depends_on = [
    google_project_service.project_0,
    google_compute_subnetwork.psci_subnet
  ]
}

############################
# LAB STATE BUCKET
############################

resource "google_storage_bucket" "state_bucket" {
  name                        = "${var.gcp_project_id}-ge-agw-state"
  location                    = var.gcp_region
  project                     = var.gcp_project_id
  force_destroy               = true
  uniform_bucket_level_access = true

  depends_on = [
    google_project_service.project_0
  ]
}
