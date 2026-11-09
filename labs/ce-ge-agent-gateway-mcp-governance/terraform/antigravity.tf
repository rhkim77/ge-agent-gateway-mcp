locals {
  instances = {
    vm1 = { name = "${var.instance_name}-1" }
  }
}

resource "google_compute_instance" "vm" {
  for_each = local.instances

  name         = "ag-vm-${each.key}"
  machine_type = var.machine_type
  zone         = var.gcp_zone

  tags = ["ag-app", "remote-browser-vm", "http-server"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = var.disk_size
      type  = "pd-ssd"
    }
  }

  service_account {
    email  = google_service_account.antigravity_sa.email
    scopes = ["cloud-platform"]
  }

  network_interface {
    network = "default"
    access_config {
      # Ephemeral public IP for Qwiklabs SSH Activity Tracking (user_0.SSH)
    }
  }

  metadata = {
    startup-script         = file("scripts/startup.sh")
    block-project-ssh-keys = "FALSE"
    enable-oslogin         = "FALSE"
    lab-username           = var.user_0_username
    lab-password           = var.user_0_password
  }

  depends_on = [
    google_project_iam_member.antigravity_sa_roles,
    google_project_service.project_0,
    google_storage_bucket.state_bucket,
    google_compute_router_nat.nat,
  ]
}

############################
# FIREWALL (shared for all VMs)
############################

resource "google_compute_firewall" "vm_firewall" {
  name    = "ag-vm-firewall"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["3000", "3001", "8080"]
  }

  source_ranges = ["10.8.0.0/28"]
  target_tags   = ["ag-app"]

  depends_on = [google_project_service.project_0]
}

resource "google_compute_firewall" "allow_ssh_qwiklabs_tracking" {
  name    = "allow-ssh-qwiklabs-tracking"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ag-app", "remote-browser-vm"]

  depends_on = [google_project_service.project_0]
}
