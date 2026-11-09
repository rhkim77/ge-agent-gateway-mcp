resource "google_service_account" "antigravity_sa" {
  account_id   = "antigravity-sa"
  display_name = "Agent Gateway Lab Workstation Service Account"
  depends_on   = [google_project_service.project_0]
}

locals {
  antigravity_sa_roles = [
    "roles/owner",
    "roles/editor",
    "roles/aiplatform.admin",
    "roles/logging.admin",
    "roles/storage.admin",
    "roles/run.admin",
    "roles/iam.serviceAccountUser",
    "roles/artifactregistry.admin",
    "roles/cloudbuild.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/modelarmor.admin",
    "roles/dlp.admin",
    "roles/discoveryengine.admin",
    "roles/bigquery.admin",
    "roles/secretmanager.admin",
    "roles/compute.admin",
    "roles/compute.networkAdmin",
    "roles/compute.securityAdmin",
    "roles/networkservices.admin",
    "roles/networkservices.serviceExtensionsAdmin",
    "roles/networksecurity.admin",
    "roles/agentregistry.admin",
    "roles/iam.accessPolicyAdmin",
    "roles/iam.securityAdmin",
    "roles/iap.admin",
    "roles/iap.egressor",
  ]
}

resource "google_project_iam_member" "antigravity_sa_roles" {
  for_each   = toset(local.antigravity_sa_roles)
  project    = var.gcp_project_id
  role       = each.key
  member     = "serviceAccount:${google_service_account.antigravity_sa.email}"
  depends_on = [google_project_service.project_0]
}

resource "google_project_iam_custom_role" "agw_admin" {
  project     = var.gcp_project_id
  role_id     = "agw_admin"
  title       = "Agent Gateway Admin"
  description = "Explicit Agent Gateway CRUD and LRO permissions"
  permissions = [
    "networkservices.agentGateways.get",
    "networkservices.agentGateways.list",
    "networkservices.agentGateways.create",
    "networkservices.agentGateways.update",
    "networkservices.agentGateways.delete",
    "networkservices.agentGateways.use",
    "networkservices.operations.get",
    "networkservices.operations.list",
  ]
  depends_on = [google_project_service.project_0]
}

resource "google_project_iam_member" "antigravity_sa_agw_admin" {
  project    = var.gcp_project_id
  role       = google_project_iam_custom_role.agw_admin.name
  member     = "serviceAccount:${google_service_account.antigravity_sa.email}"
  depends_on = [google_project_iam_custom_role.agw_admin]
}

data "google_compute_default_service_account" "default" {
  depends_on = [google_project_service.project_0]
}

resource "google_project_iam_member" "def-sa-compute-owner-bind" {
  project    = var.gcp_project_id
  role       = "roles/owner"
  member     = "serviceAccount:${data.google_compute_default_service_account.default.email}"
  depends_on = [google_project_service.project_0]
}

# Enable Data Access audit logs (ADMIN_READ, DATA_WRITE, DATA_READ) across all services
resource "google_project_iam_audit_config" "all_services_audit" {
  project = var.gcp_project_id
  service = "allServices"
  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
  depends_on = [google_project_service.project_0]
}
