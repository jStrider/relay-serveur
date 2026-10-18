data "ovh_me" "me" {}

# Le plus petit VPS suffit : une app Python, un fichier SQLite, Caddy.
resource "ovh_vps" "relay" {
  display_name   = "relay"
  ovh_subsidiary = data.ovh_me.me.ovh_subsidiary

  plan = [{
    plan_code    = "vps-2027-model1"
    duration     = "P1M"
    pricing_mode = "default"
    configuration = [
      { label = "vps_datacenter", value = var.vps_datacenter },
      { label = "vps_os", value = "Debian 13" },
    ]
  }]

  plan_option = [
    { plan_code = "option-linux", duration = "P1M", pricing_mode = "default", quantity = 1 },
    { plan_code = "option-auto-backup-2027-1-model1", duration = "P1M", pricing_mode = "default", quantity = 1 },
  ]

  image_id       = var.vps_image_id
  public_ssh_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "ovh_domain_zone_record" "relay" {
  zone      = var.zone
  subdomain = var.sous_domaine
  fieldtype = "CNAME"
  ttl       = 60
  target    = "${ovh_vps.relay.service_name}."
}

# Sauvegardes : bucket en région 3-AZ, séparé du VPS.
resource "random_id" "bucket" {
  byte_length = 4
}

resource "ovh_cloud_project_storage" "backups" {
  service_name = var.cloud_project_id
  region_name  = "EU-WEST-PAR"
  name         = "relay-backups-${random_id.bucket.hex}"
  hide_objects = true
}

resource "ovh_cloud_project_user" "backups" {
  service_name = var.cloud_project_id
  description  = "restic relay"
  role_names   = ["objectstore_operator"]
}

resource "ovh_cloud_project_user_s3_credential" "backups" {
  service_name = var.cloud_project_id
  user_id      = ovh_cloud_project_user.backups.id
}

resource "ovh_cloud_project_user_s3_policy" "backups" {
  service_name = var.cloud_project_id
  user_id      = ovh_cloud_project_user.backups.id
  policy = jsonencode({
    Statement = [{
      Sid    = "ResticBackups"
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:ListMultipartUploadParts", "s3:ListBucketMultipartUploads", "s3:AbortMultipartUpload", "s3:GetBucketLocation"]
      Resource = [
        "arn:aws:s3:::${ovh_cloud_project_storage.backups.name}",
        "arn:aws:s3:::${ovh_cloud_project_storage.backups.name}/*",
      ]
    }]
  })
}
