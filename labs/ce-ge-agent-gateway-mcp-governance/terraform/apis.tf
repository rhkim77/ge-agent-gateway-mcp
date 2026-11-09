# ********** Enable Google Cloud APIs ************
variable "gcp_project_default_services" {
  type        = list(any)
  description = "APIs (<api>.googleapis.com) to enable for Agent Registry, Agent Gateway, Cloud Armor, Model Armor, SDP, and Gemini Enterprise"
  default = [
    "cloudresourcemanager.googleapis.com",
    "storage.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "discoveryengine.googleapis.com",
    "cloudapiregistry.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "modelarmor.googleapis.com",
    "dlp.googleapis.com",
    "agentregistry.googleapis.com",
    "apphub.googleapis.com",
    "agentidentity.googleapis.com",
    "iap.googleapis.com",
    "networksecurity.googleapis.com",
    "networkservices.googleapis.com",
    "networkconnectivity.googleapis.com",
    "serviceextensions.googleapis.com",
    "dns.googleapis.com",
    "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com",
    "cloudbuild.googleapis.com",
    "bigquery.googleapis.com",
    "serviceusage.googleapis.com",
    "orgpolicy.googleapis.com"
  ]
}

data "google_project" "project_0" {
  project_id = var.gcp_project_id
}

resource "google_project_service" "project_0" {
  project  = data.google_project.project_0.project_id
  for_each = toset(var.gcp_project_default_services)
  service  = each.value

  disable_on_destroy = false
}
