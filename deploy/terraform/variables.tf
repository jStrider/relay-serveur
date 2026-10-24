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

variable "region" {
  description = "Région Public Cloud en France (GRA9 Gravelines, SBG5 Strasbourg) : les données restent en France (politique de confidentialité)."
  type        = string
  default     = "GRA9"

  validation {
    condition     = can(regex("^(GRA|SBG)", var.region))
    error_message = "Région en France seulement : GRA… ou SBG…."
  }
}

variable "flavor_id" {
  description = "Gabarit d2-2 (1 vCPU, 2 Go) de la région (GET /cloud/project/{id}/flavor?region=…)."
  type        = string
  default     = "fbb7940b-4268-437c-85f8-8c27fcef0dcd"
}

variable "image_id" {
  description = "Image Debian 13 de la région (GET /cloud/project/{id}/image?region=…). Sa modification réinstalle l'instance."
  type        = string
  default     = "aeab2d2c-b168-4f4a-8408-f6a50327266e"
}
