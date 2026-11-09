output "private" {
  description = "Private IP of the VM"
  value       = google_compute_instance.vm["vm1"].network_interface[0].network_ip
}

output "service_url" {
  value       = google_cloud_run_service.service["vm1"].status[0].url
  description = "URL of the Incognito proxy"
}

output "remote_browser_url" {
  value       = google_cloud_run_service.service["vm1"].status[0].url
  description = "URL of the Cloud Run remote browser proxy (remote-browser-vm1)"
}

output "state_bucket_name" {
  description = "Pre-provisioned GCS bucket for lab state and Qwiklabs assessment sync"
  value       = google_storage_bucket.state_bucket.name
}

output "agw_static_egress_ip" {
  description = "Static Cloud NAT /32 Egress IP for AWS Security Group allowlisting"
  value       = google_compute_address.agw_egress_ip.address
}
