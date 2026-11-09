resource "google_cloud_run_service" "service" {
  for_each = google_compute_instance.vm

  name     = "remote-browser-${each.key}"
  location = var.gcp_region
  project  = var.gcp_project_id

  metadata {
    annotations = {
      "run.googleapis.com/ingress" = "all"
    }
  }

  template {
    spec {
      service_account_name  = data.google_compute_default_service_account.default.email
      container_concurrency = 2
      timeout_seconds       = 300

      containers {
        image = "us-docker.pkg.dev/qwiklabs-resources/lfs-images/nginx-reverse-proxy:latest"

        ports {
          container_port = 8080
        }

        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }

        env {
          name  = "EXTERNAL_IP"
          value = google_compute_instance.vm[each.key].network_interface[0].network_ip
        }

        env {
          name  = "FRONTEND_PORT"
          value = "8080"
        }

        env {
          name  = "BACKEND_PORT"
          value = "3000"
        }
      }
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale"        = "1"
        "autoscaling.knative.dev/maxScale"        = "2"
        "run.googleapis.com/vpc-access-connector" = google_vpc_access_connector.connector.id
        "run.googleapis.com/vpc-access-egress"    = "all-traffic"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_project_service.run,
    google_vpc_access_connector.connector,
    google_project_iam_member.def-sa-compute-owner-bind,
  ]
}

data "google_iam_policy" "noauth" {
  binding {
    role    = "roles/run.invoker"
    members = ["allUsers"]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth" {
  for_each = google_cloud_run_service.service

  location    = each.value.location
  project     = each.value.project
  service     = each.value.name
  policy_data = data.google_iam_policy.noauth.policy_data
}
