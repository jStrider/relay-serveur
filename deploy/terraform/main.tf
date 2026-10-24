# La plus petite instance Public Cloud suffit : une app Python, un fichier SQLite, Caddy. (Les VPS étaient en
# rupture partout en France à la création, en octobre 2026.) Région française : les données restent en France.
resource "ovh_cloud_project_instance" "relay" {
  service_name   = var.cloud_project_id
  region         = var.region
  name           = "relay"
  billing_period = "monthly"

  flavor {
    flavor_id = var.flavor_id
  }
  boot_from {
    image_id = var.image_id
  }
  network {
    public = true
  }
  ssh_key_create {
    name       = "relay"
    public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
  }
  # Instantané quotidien gardé 7 jours (durée annoncée dans la politique de confidentialité).
  auto_backup {
    cron     = "0 4 * * *"
    rotation = 7
  }
}

locals {
  ipv4 = one([for a in ovh_cloud_project_instance.relay.addresses : a.ip if a.version == 4])
  ipv6 = one([for a in ovh_cloud_project_instance.relay.addresses : a.ip if a.version == 6])
}

# Le relais (relay.<zone>) et le site (racine du domaine, servi par Caddy sur la même instance) ; www redirige.
resource "ovh_domain_zone_record" "adresses" {
  for_each  = { "relais-A" = [var.sous_domaine, "A"], "relais-AAAA" = [var.sous_domaine, "AAAA"], "site-A" = ["", "A"], "site-AAAA" = ["", "AAAA"] }
  zone      = var.zone
  subdomain = each.value[0]
  fieldtype = each.value[1]
  ttl       = 300
  target    = each.value[1] == "A" ? local.ipv4 : local.ipv6
}

resource "ovh_domain_zone_record" "www" {
  zone      = var.zone
  subdomain = "www"
  fieldtype = "CNAME"
  ttl       = 300
  target    = "${var.zone}."
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
