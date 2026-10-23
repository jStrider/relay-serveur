variable "cloud_project_id" {
  description = "Projet Public Cloud qui porte le bucket de sauvegarde."
  type        = string
}

variable "zone" {
  description = "Zone DNS gérée chez OVH (le domaine de Relay)."
  type        = string
}

variable "sous_domaine" {
  description = "Sous-domaine du relais dans la zone : relay.<zone>."
  type        = string
  default     = "relay"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/hermes_ed25519.pub"
}

variable "vps_image_id" {
  description = "Image Debian 13 (GET /vps/{service}/images/available). Sa modification réinstalle le VPS."
  type        = string
  default     = "f4dfe914-e786-4723-ad93-f01576604800"
}

variable "vps_datacenter" {
  description = "GRA (Gravelines) ou SBG (Strasbourg) : les données de santé chiffrées restent en France (politique de confidentialité)."
  type        = string
  default     = "GRA"

  validation {
    condition     = contains(["GRA", "SBG"], var.vps_datacenter)
    error_message = "Centre de données en France seulement : GRA ou SBG."
  }
}
