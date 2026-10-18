output "host" {
  value = ovh_vps.relay.service_name
}

output "nom_public" {
  value = "${var.sous_domaine}.${var.zone}"
}

output "restic_repository" {
  value = "s3:https://s3.eu-west-par.io.cloud.ovh.net/${ovh_cloud_project_storage.backups.name}"
}

output "s3_access_key_id" {
  value = ovh_cloud_project_user_s3_credential.backups.access_key_id
}

output "s3_secret_access_key" {
  value     = ovh_cloud_project_user_s3_credential.backups.secret_access_key
  sensitive = true
}
